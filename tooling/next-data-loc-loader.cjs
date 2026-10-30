// Webpack loader that stamps every intrinsic JSX element with data-loc="file:line:column" (dev only).
// Runs as a PRE loader, i.e. on the original source before Next's SWC loader. Babel and its syntax plugins resolve
// from Fixel's own node_modules, never the target's. A file Babel cannot parse is passed through untouched with a
// warning, so this can never break the target's build.
const path = require('node:path');
const babel = require('@babel/core');
const dataLoc = require('./babel-plugin-data-loc.cjs');

const syntaxJsx = require.resolve('@babel/plugin-syntax-jsx');
const syntaxTs = require.resolve('@babel/plugin-syntax-typescript');

module.exports = function fixelDataLocLoader(source, inputMap) {
  const done = this.async();
  const file = this.resourcePath;
  const root = (this.getOptions && this.getOptions().root) || this.rootContext || process.cwd();
  const plugins = [[syntaxJsx], [dataLoc]];
  if (file.endsWith('.tsx')) plugins.unshift([syntaxTs, { isTSX: true }]);
  try {
    const out = babel.transformSync(source, {
      filename: file, cwd: root, plugins, babelrc: false, configFile: false, sourceType: 'module',
      compact: false, retainLines: true, sourceMaps: this.sourceMap,
      inputSourceMap: inputMap && typeof inputMap === 'object' ? inputMap : undefined,
    });
    done(null, out ? out.code : source, out && out.map ? out.map : inputMap);
  } catch (e) {
    this.emitWarning(new Error(`fixel data-loc skipped ${path.relative(root, file)}: ${e.message.split('\n')[0]}`));
    done(null, source, inputMap);
  }
};
