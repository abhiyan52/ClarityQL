import { useState } from "react";
import Dashboard from "./pages/Dashboard";
import Login from "./pages/Login";

const App = () => {
  const [isAuthenticated] = useState(false);

  return (
    <div style={{ fontFamily: "system-ui, sans-serif", padding: "2rem" }}>
      <h1>ClarityQL</h1>
      {isAuthenticated ? <Dashboard /> : <Login />}
    </div>
  );
};

export default App;
