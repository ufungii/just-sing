/** Resolve APIs for both /live/ standalone and /karaoke/live/ mounted previews. */
export function apiUrl(path, moduleUrl = import.meta.url) {
  return new URL(path.replace(/^\/api\//, ""), new URL("../api/", moduleUrl)).href;
}
