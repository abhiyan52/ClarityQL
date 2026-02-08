
import asyncio
import sys
import os
from unittest.mock import MagicMock, patch
from uuid import uuid4
from datetime import datetime

# Add app and root to path
backend_dir = os.path.abspath(os.path.join(os.path.dirname(__file__), "../"))
project_root = os.path.abspath(os.path.join(backend_dir, "../../"))
sys.path.append(backend_dir)
sys.path.append(project_root)

from httpx import AsyncClient, ASGITransport
from sqlalchemy import text
from sqlalchemy.ext.asyncio import create_async_engine, AsyncSession
from sqlalchemy.orm import sessionmaker

from app.main import app
from app.core.dependencies import get_current_user, get_async_session
from app.db.base import Base
from app.db.session import async_session_factory
from app.models.user import User
from app.models.tenant import Tenant
from app.models.conversation import Conversation
from app.models.message import Message

async def run_tests():
    # Setup Mock User and Tenant
    mock_user_id = uuid4()
    mock_tenant_id = uuid4()
    mock_email = f"test_{mock_user_id}@example.com"
    
    print(f"Using Test User ID: {mock_user_id}")
    print(f"Using Test Tenant ID: {mock_tenant_id}")

    mock_user = User(id=mock_user_id, email=mock_email, tenant_id=mock_tenant_id)

    async def override_get_current_user():
        return mock_user

    # Initialize Data in Real DB
    print("Initializing Test Data in Real DB...")
    async with async_session_factory() as session:
        # Create Tenant
        tenant = Tenant(id=mock_tenant_id, name="Test Tenant", slug=f"test-tenant-{mock_tenant_id}")
        session.add(tenant)
        # Create User
        user = User(id=mock_user_id, email=mock_email, tenant_id=mock_tenant_id, hashed_password="mock_hash")
        session.add(user)
        await session.commit()

    # Override dependencies
    # We DO NOT override get_async_session, so it uses real DB
    app.dependency_overrides[get_current_user] = override_get_current_user

    async def cleanup():
        print("\nCleaning up Test Data...")
        try:
            async with async_session_factory() as session:
                await session.execute(
                    text(f"DELETE FROM users WHERE id = '{mock_user_id}'")
                )
                await session.execute(
                    text(f"DELETE FROM tenants WHERE id = '{mock_tenant_id}'")
                )
                await session.commit()
        except Exception as e:
            print(f"Cleanup failed: {e}")

    transport = ASGITransport(app=app)
    try:
        async with AsyncClient(transport=transport, base_url="http://test") as client:
            print("\n--- Testing Conversation Flow ---")

            # 1. Create a query (creates conversation)
            print("\n1. Submitting Query...")
            
            with patch("app.tasks.nlq_tasks.process_nlq_query_task") as mock_celery:
                # We need to mock the apply_async return value
                mock_result = MagicMock()
                mock_result.id = f"test-task-{uuid4()}"
                mock_celery.apply_async.return_value = mock_result
                
                response = await client.post(
                    "/api/nlq/query",
                    json={"query": "Show me total sales"},
                )
                print(f"Query Response: {response.status_code} {response.json()}")
                assert response.status_code == 202
                data = response.json()
                assert "conversation_id" in data
                conversation_id = data["conversation_id"]
                task_id = data["task_id"]
                print(f"Created Conversation: {conversation_id}")
                print(f"Created Task: {task_id}")

            # 2. List Conversations
            print("\n2. Listing Conversations...")
            response = await client.get("/api/nlq/conversations")
            print(f"List Response: {response.status_code} {response.json()}")
            assert response.status_code == 200
            conversations = response.json()
            assert len(conversations) > 0
            # Convert UUID strings to compare if needed, but JSON returns strings
            # Check if our created conversation is in the list
            found = False
            for conv in conversations:
                if conv["id"] == conversation_id:
                    found = True
                    assert conv["title"] == "New Conversation"
                    break
            assert found, f"Conversation {conversation_id} not found in list"

            # 3. Get Conversation Details
            print(f"\n3. Getting Conversation Details for {conversation_id}...")
            response = await client.get(f"/api/nlq/conversations/{conversation_id}")
            print(f"Details Response: {response.status_code} {response.json()}")
            assert response.status_code == 200
            details = response.json()
            assert details["id"] == conversation_id
            assert "messages" in details
            
            # Manually verify we can add a message to the DB to check retrieval
            async with async_session_factory() as session:
                msg = Message(conversation_id=conversation_id, role="user", content="Test Message")
                session.add(msg)
                await session.commit()

            response = await client.get(f"/api/nlq/conversations/{conversation_id}")
            details = response.json()
            # Verify message is there
            assert len(details["messages"]) > 0
            print(f"Messages found: {len(details['messages'])}")

            # 4. Delete Conversation
            print(f"\n4. Deleting Conversation {conversation_id}...")
            response = await client.delete(f"/api/nlq/conversations/{conversation_id}")
            assert response.status_code == 200
            
            # Verify deletion
            response = await client.get(f"/api/nlq/conversations/{conversation_id}")
            assert response.status_code == 404
            print("Conversation deleted successfully.")

            # 5. List again to confirm empty
            response = await client.get("/api/nlq/conversations")
            conversations = response.json()
            found = False
            for conv in conversations:
                if conv["id"] == conversation_id:
                    found = True
                    break
            assert not found, "Conversation still exists in list"
            print("Conversation confirmed deleted.")

            print("\n--- Test Completed Successfully ---")

    except Exception as e:
        print(f"\nTest Failed: {e}")
        import traceback
        traceback.print_exc()
        # Non-zero exit code if test fails
        sys.exit(1)
    finally:
        await cleanup()

if __name__ == "__main__":
    asyncio.run(run_tests())
