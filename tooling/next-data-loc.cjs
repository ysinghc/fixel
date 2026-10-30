// Node preload (NODE_OPTIONS=--require this file) that adds the data-loc webpack loader to a Next.js app WITHOUT
// editing the app. Vite targets use tooling/vite.config.fixel.mjs; Next has no --config flag, hence this hook.
//
// How: Next loads and normalizes the user's next.config.* in next/dist/server/config (loadConfig). That module is
// required by Next's own CommonJS code, so we wrap loadConfig and, for the app we are scanning, wrap the webpack()
// hook of the config it returns, to prepend a pre-loader rule that stamps data-loc. Hooking the *result* means every
// way a config can be written works: object, function, async function, CommonJS, ESM (.mjs), TypeScript.
// (Wrapping the user's config module instead does not work: Next loads it with a native import(), and Node's ESM
// bridge reads module.exports from its own path, ignoring what a patched Module._load returns.)
//
// Active only when FIXEL=1 and FIXEL_APP_ROOT names the app directory, and the webpack rule only applies in dev.
const fs = require('node:fs');
const Module = require('node:module');
const path = require('node:path');

const LOADER = path.join(__dirname, 'next-data-loc-loader.cjs');
const real = (p) => { try { return fs.realpathSync(p); } catch (_) { return path.resolve(p); } };
const APP_ROOT = process.env.FIXEL_APP_ROOT && real(process.env.FIXEL_APP_ROOT);

function inject(webpackConfig, opts) {
  if (!opts || !opts.dev) return webpackConfig;                       // dev only, like the Vite plugin
  webpackConfig.module = webpackConfig.module || {};
  webpackConfig.module.rules = webpackConfig.module.rules || [];
  webpackConfig.module.rules.unshift({
    test: /\.(jsx|tsx)$/,
    include: [APP_ROOT],
    exclude: /node_modules/,
    enforce: 'pre',                                                    // runs on the original source, before Next's SWC loader
    use: [{ loader: LOADER, options: { root: APP_ROOT } }],
  });
  return webpackConfig;
}

// Wrap a normalized Next config's webpack() hook (idempotent).
function patchConfig(cfg) {
  if (!cfg || typeof cfg !== 'object' || (cfg.webpack && cfg.webpack.__fixel)) return cfg;
  const original = cfg.webpack;
  const hook = function fixelWebpack(config, opts) {
    const out = typeof original === 'function' ? original.call(this, config, opts) : config;
    return inject(out || config, opts);
  };
  hook.__fixel = true;
  cfg.webpack = hook;
  return cfg;
}

// A stand-in for next/dist/server/config whose default export (loadConfig) patches the app's config.
function patchConfigModule(mod) {
  const loadConfig = mod.default;
  const wrapped = async function fixelLoadConfig(phase, dir, ...rest) {
    const cfg = await loadConfig.call(this, phase, dir, ...rest);
    return typeof dir === 'string' && real(dir) === APP_ROOT ? patchConfig(cfg) : cfg;
  };
  const out = {};
  for (const key of Object.getOwnPropertyNames(mod)) {
    if (key === '__esModule') continue;
    Object.defineProperty(out, key, { enumerable: true, get: () => (key === 'default' ? wrapped : mod[key]) });
  }
  Object.defineProperty(out, '__esModule', { value: true });
  return out;
}

const isNextConfigModule = (file) => /[\\/]next[\\/]dist[\\/]server[\\/]config\.js$/.test(file);
const patched = new WeakMap();

if (process.env.FIXEL === '1' && APP_ROOT) {
  const load = Module._load;
  Module._load = function patchedLoad(request, parent, isMain) {
    const exported = load.apply(this, arguments);
    if (typeof request === 'string' && /config(\.js)?$/.test(request)) {            // cheap filter before resolving
      try {
        if (exported && exported.__esModule && typeof exported.default === 'function'
            && isNextConfigModule(Module._resolveFilename(request, parent, isMain))) {
          if (!patched.has(exported)) patched.set(exported, patchConfigModule(exported));
          return patched.get(exported);
        }
      } catch (_) { /* not resolvable: not Next's config module */ }
    }
    return exported;
  };
}

module.exports = { inject, patchConfig, patchConfigModule, LOADER };
