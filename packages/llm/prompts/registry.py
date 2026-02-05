"""Prompt registry for version management."""

from typing import Callable

from .base import BasePrompt


class PromptRegistry:
    """
    Registry for prompt versions.

    Allows registering and retrieving prompt versions by name.
    Supports "latest" as an alias for the most recent version.
    """

    _prompts: dict[str, type[BasePrompt]] = {}

    @classmethod
    def register(cls, prompt_class: type[BasePrompt]) -> type[BasePrompt]:
        """
        Register a prompt class.

        Can be used as a decorator:
            @PromptRegistry.register
            class PromptV1(BasePrompt):
                version = "v1"
                ...

        Args:
            prompt_class: The prompt class to register.

        Returns:
            The same prompt class (for decorator usage).
        """
        version = prompt_class.version
        cls._prompts[version] = prompt_class
        return prompt_class

    @classmethod
    def get(cls, version: str = "latest") -> BasePrompt:
        """
        Get a prompt instance by version.

        Args:
            version: Version string (e.g., "v1", "v2") or "latest".

        Returns:
            An instance of the requested prompt version.

        Raises:
            ValueError: If the version is not registered.
        """
        if not cls._prompts:
            raise ValueError("No prompts registered")

        if version == "latest":
            # Sort versions and get the highest
            sorted_versions = sorted(
                cls._prompts.keys(),
                key=cls._version_sort_key,
            )
            version = sorted_versions[-1]

        if version not in cls._prompts:
            available = ", ".join(sorted(cls._prompts.keys()))
            raise ValueError(
                f"Unknown prompt version: {version}. Available: {available}"
            )

        return cls._prompts[version]()

    @classmethod
    def list_versions(cls) -> list[str]:
        """List all registered prompt versions."""
        return sorted(cls._prompts.keys(), key=cls._version_sort_key)

    @classmethod
    def _version_sort_key(cls, version: str) -> tuple:
        """
        Sort key for version strings.

        Handles versions like "v1", "v2", "v10" correctly.
        """
        # Extract numeric part from version string
        if version.startswith("v"):
            try:
                return (0, int(version[1:]))
            except ValueError:
                pass
        return (1, version)

    @classmethod
    def clear(cls) -> None:
        """Clear all registered prompts. Useful for testing."""
        cls._prompts.clear()
