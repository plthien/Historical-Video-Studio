# Frozen visual registries

- layouts.v1.json: exactly **30 concrete combinations** (T01–T10 x variants A/B/C) using TemplateLayout.v1 for positions/slot/kinds/safe-area and bounded camera rules. The registry is design input to compiler, not implemented React/Remotion components.
- motion-presets.v1.json: 19 supported motion presets, layer compatibility and parameter/easing limits. Rendering code expands these into integer-frame keyframes and obeys reduced motion.
- Source captions, archive provenance and period maps are independent approval contracts; template layout fallback NEVER authorizes substituting a historical asset.

Version increments on breaking visual grammar; compiler hash binds both registry versions.

**V1.1 repair:** every template variant has custom slot geometry/required role cardinality and layout relation (not 3 recycled boxes); 19 motion presets each include typed parameter_schema, render primitive, phase recipe and transform space. Geographic route and editorial annotation connector are deliberately different layer types/presets; tests fail closed on misuse.
