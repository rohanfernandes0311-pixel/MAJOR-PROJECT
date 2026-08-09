"""Optional extension layer for LandSense.

The modules in this package are deliberately decoupled from the core
Phase 1 workflow. They provide lazy-loaded adapters, safe fallbacks,
and enterprise-style wrapper services that can be adopted incrementally
without changing the existing behavior of the application.

Import concrete modules directly, for example:
`from services.extension_loader import ExtensionLoader`
"""

