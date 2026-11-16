export function createLifecycleSafeCanvas(L) {
  const LifecycleSafeCanvas = L.Canvas.extend({
    _redraw() {
      // Leaflet also calls _redraw synchronously from _updatePaths. Its base
      // implementation clears _redrawRequest without cancelling a queued frame,
      // losing the handle needed by _destroyContainer during map teardown.
      L.Util.cancelAnimFrame(this._redrawRequest)
      return L.Canvas.prototype._redraw.call(this)
    }
  })
  return new LifecycleSafeCanvas()
}
