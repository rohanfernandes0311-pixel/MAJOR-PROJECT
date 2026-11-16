import test from 'node:test'
import assert from 'node:assert/strict'
import { readFileSync } from 'node:fs'
import { createLifecycleSafeCanvas } from './leafletCanvasLifecycle.js'

function leafletFixture() {
  const frames = new Map()
  let next = 0
  let draws = 0
  function Renderer() {}
  Renderer.extend = function (methods) {
    function Child() { this._layers = {} }
    Child.prototype = Object.assign(Object.create(this.prototype), methods)
    Child.extend = this.extend
    return Child
  }
  const Util = {
    requestAnimFrame: (fn, context) => { frames.set(++next, () => fn.call(context)); return next },
    cancelAnimFrame: id => frames.delete(id)
  }
  // Exercise the installed Leaflet implementation, including its actual
  // synchronous redraw and destroy methods, without requiring browser globals.
  const source = readFileSync(new URL('../../node_modules/leaflet/src/layer/vector/Canvas.js', import.meta.url), 'utf8')
    .replace(/^import .*;\r?$/gm, '').replace(/export /g, '')
  const Canvas = new Function('Renderer', 'DomUtil', 'DomEvent', 'Browser', 'Util', 'Bounds', `${source}\nreturn Canvas`)(
    Renderer, { remove() {} }, { off() {} }, { canvas: true }, Util, class {}
  )
  const L = { Canvas, Util }
  function prepare(renderer) {
    renderer._map = {}
    renderer._container = { width: 100, height: 100 }
    renderer._ctx = { save() {}, restore() {}, setTransform() {}, clearRect() { draws++ } }
    return renderer
  }
  function flush() {
    for (const [id, callback] of [...frames]) { frames.delete(id); callback() }
  }
  return { L, frames, prepare, flush, draws: () => draws }
}

test('installed Leaflet loses a queued frame on synchronous redraw and fails after destruction', () => {
  const f = leafletFixture()
  const renderer = f.prepare(new f.L.Canvas())
  renderer._requestRedraw({})
  renderer._updatePaths()
  assert.equal(f.frames.size, 1)
  renderer._requestRedraw({})
  renderer._destroyContainer()
  assert.equal(f.frames.size, 1)
  assert.throws(f.flush, TypeError)
})

test('lifecycle-safe canvas draws normally and cancels every queued frame before destruction', () => {
  const f = leafletFixture()
  for (let i = 0; i < 100; i++) {
    const renderer = f.prepare(createLifecycleSafeCanvas(f.L))
    renderer._requestRedraw({})
    f.flush()
    renderer._requestRedraw({})
    renderer._updatePaths()
    assert.equal(f.frames.size, 0)
    renderer._requestRedraw({})
    renderer._destroyContainer()
    assert.equal(f.frames.size, 0)
    assert.doesNotThrow(f.flush)
  }
  assert.equal(f.draws(), 200)
})
