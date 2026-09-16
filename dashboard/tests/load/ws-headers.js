// Reads session cookies from env vars and injects a Cookie header per scenario
module.exports = {
  useRc: (context, events, done) => {
    const sid = process.env.RC_SESSION;
    if (!sid) { throw new Error("RC_SESSION env var missing"); }
    context.vars.cookie = `sessionid=${sid}`;
    return done();
  },
  useEx: (context, events, done) => {
    const sid = process.env.EX_SESSION;
    if (!sid) { throw new Error("EX_SESSION env var missing"); }
    context.vars.cookie = `sessionid=${sid}`;
    return done();
  }
};
