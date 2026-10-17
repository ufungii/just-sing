// JUST_SING_URL is baked into this build, with a runtime environment override.
// Only the desktop shell ships: the API, song assets and secrets stay on the server.
module.exports = {
  appId: 'dev.justsing.desktop',
  productName: 'Just Sing',
  directories: { output: 'dist' },
  files: ['main.js', 'preload.js', 'offline.html', 'package.json'],
  extraMetadata: {
    justSingUrl: process.env.JUST_SING_URL || 'http://localhost:8000',
  },
  linux: {
    target: ['AppImage'],
    category: 'Game',
    artifactName: 'Just-Sing-${version}-${arch}.${ext}',
  },
};
