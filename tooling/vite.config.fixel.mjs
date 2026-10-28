// Wrapper config: loads the target's own Vite config (path in FIXEL_TARGET_CONFIG) and prepends the
// data-loc plugin. Run as: FIXEL_TARGET_CONFIG=<abs path> vite --config <this file> (cwd = target dir).
import { pathToFileURL } from 'node:url';
import dataLoc from './vite-plugin-data-loc.mjs';

const target = process.env.FIXEL_TARGET_CONFIG;
const user = target ? (await import(pathToFileURL(target).href)).default : {};

export default async (env) => {
  const cfg = typeof user === 'function' ? await user(env) : user;
  return { ...cfg, plugins: [dataLoc({ root: process.cwd() }), ...(cfg.plugins ?? [])] };
};
