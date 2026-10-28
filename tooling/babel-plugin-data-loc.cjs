const path = require('path');
module.exports = function dataLoc({ types: t }) {
  return {
    name: 'data-loc',
    visitor: {
      JSXOpeningElement(p, state) {
        const n = p.node.name;
        if (n.type !== 'JSXIdentifier' || !/^[a-z]/.test(n.name)) return;      // intrinsic tags only
        if (p.node.attributes.some(a => a.type === 'JSXAttribute' && a.name.name === 'data-loc')) return;
        const file = state.filename || state.file.opts.filename;
        const cwd = state.cwd || state.file.opts.cwd || process.cwd();
        const { line, column } = p.node.loc.start;
        p.node.attributes.push(t.jsxAttribute(t.jsxIdentifier('data-loc'),
          t.stringLiteral(`${path.relative(cwd, file)}:${line}:${column + 1}`)));
      },
    },
  };
};
