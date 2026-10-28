// Vite plugin that stamps every intrinsic JSX element with data-loc="file:line:column" (dev only).
// It runs Babel itself, before the framework's own transform, so it works with plugin-react v4/v5
// (Babel), v6 (Oxc, no babel option) and plugin-react-swc alike. Babel and the syntax plugins resolve
// from Fixel's own node_modules, never the target's.
import { createRequire } from 'node:module';
import path from 'node:path';

const require = createRequire(import.meta.url);
const babel = require('@babel/core');
const dataLoc = require('./babel-plugin-data-loc.cjs');
const syntaxJsx = require.resolve('@babel/plugin-syntax-jsx');
const syntaxTs = require.resolve('@babel/plugin-syntax-typescript');

export default function fixelDataLoc({ root = process.cwd() } = {}) {
  return {
    name: 'fixel-data-loc',
    enforce: 'pre',
    apply: 'serve',
    async transform(code, id) {
      const file = id.split('?')[0];
      if (!/\.[jt]sx$/.test(file) || file.includes('/node_modules/')) return null;
      const plugins = [[syntaxJsx], [dataLoc]];
      if (file.endsWith('.tsx')) plugins.unshift([syntaxTs, { isTSX: true }]);
      const out = await babel.transformAsync(code, {
        filename: file, cwd: root, plugins, babelrc: false, configFile: false,
        sourceMaps: true, sourceType: 'module', compact: false, retainLines: true,
      });
      return out ? { code: out.code, map: out.map } : null;
    },
  };
}
