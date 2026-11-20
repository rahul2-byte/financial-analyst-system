// Empty stand-in for Ink's optional peer dependency `react-devtools-core`.
// esbuild's `alias` in esbuild.config.mjs points at this file so `npm run
// build` succeeds without the package installed; devtools stay disabled.
export default {
  initialize() {
    /* no-op */
  },
  connectToDevTools() {
    /* no-op */
  },
};
