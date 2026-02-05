const Login = () => {
  return (
    <section>
      <h2>Login</h2>
      <p>Authenticate to access your analytics workspace.</p>
      <form>
        <label>
          Email
          <input type="email" placeholder="you@company.com" />
        </label>
        <label>
          Password
          <input type="password" placeholder="••••••••" />
        </label>
        <button type="button">Sign in</button>
      </form>
    </section>
  );
};

export default Login;
