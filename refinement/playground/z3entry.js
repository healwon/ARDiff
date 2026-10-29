// browser entry: exposes window.Z3Lite.evalFactory() -> async (smt) => output
const { init } = require('z3-solver/build/browser.js');
window.Z3Lite = {
  async evalFactory() {
    const { Z3 } = await init();
    return async (smt) => {
      const cfg = Z3.mk_config(); const ctx = Z3.mk_context(cfg); Z3.del_config(cfg);
      Z3.global_param_set('timeout', '8000');
      try { return await Z3.eval_smtlib2_string(ctx, smt); } finally { Z3.del_context(ctx); }
    };
  }
};
