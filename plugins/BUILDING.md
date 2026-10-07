# PSP JSON module builds on Windows

Use the same entry points as the PS2 SDK module builder:

```powershell
powershell -NoProfile -ExecutionPolicy Bypass -File external/pspsdk/plugins/build-module.ps1 -Project source/module.json
powershell -NoProfile -ExecutionPolicy Bypass -File external/pspsdk/plugins/build-module.ps1 -Project source/module.json -Clean
```

Paths in `module.json` are relative to that file, regardless of the caller's
working directory. Projects may reside in folders containing spaces. Sources
are explicit; add new files to the manifest. C helpers always use the C compiler,
even in a C++ project. Assembly sources are supported too.

```json
{
  "sources": ["main.c", "includes/injector.c"],
  "output": "../data/memstick/PSP/PLUGINS/MyPlugin/MyPlugin.prx",
  "exports": "exports.exp",
  "startup": "module_start",
  "libraries": ["-lpspsystemctrl_user", "-lm"]
}
```

The common PS2/PSP fields are `sources`, `output`, `includes`, `defines` and
`link_options`. PSP additionally uses `exports`, `startup` and `libraries`.
Optional `c_flags` replaces the default C flags; `cxx_flags` supplies additional
C++ flags (defaults to disabling exceptions/RTTI), and `as_flags` adds assembly
flags. Unknown fields fail instead of silently ignoring a misspelling.

The default configuration is Release (`NDEBUG`). Pass `-Configuration Debug`
to define `DEBUG` and `_DEBUG` and emit debug symbols. Both configurations retain
the existing optimized code flags and write the same output paths; the builder
recompiles everything, so switching configuration cannot reuse stale objects.
The configuration defines are applied after manifest defines. WFP and generated
Visual Studio projects pass their selected configuration to this entry point.
These defines let plugins omit selected diagnostic calls in Release builds.
The shared logger remains available in either configuration.

`PSP_MODULE_INFO` accepts a string literal or a macro expanding to one in both
C and C++. Use `PSP_MODULE_INFO("CLEO", ...)`, rather than an unquoted identifier.
The C++ metadata initializer requires C++14 or later and is evaluated at compile
time; it adds no constructors or startup code. Names may contain at most 27
characters, with the terminating byte retained in the original module-info ABI.

`startup: "module_start"` follows the existing `build_prx.mak` profile with no
CRT startup files. The plugin supplies `module_start`. This is the default and
preserves WidescreenFixesPack's C PRX behavior. `startup: "crt"` follows the
existing `build.mak` PRX profile, linking the SDK startup files so `main`, heap
initialization and C++ constructors work as before. PSP CLEO and C++ template
projects use this profile. C++ compilation alone does not change the startup
profile; choose it explicitly.

Minimal C++ modules additionally link a small constructor startup wrapper.
The builder renames the supplied entry point internally; keep writing
`extern "C" int module_start(SceSize, void*)` and exporting `module_start`.
Static constructors run once before that entry point. Destructor registration
uses 128 fixed slots in the module image; overflowing them rejects startup.
There is no system heap initialization. Use the plugin's bounded allocator for
dynamic storage. `__cxa_finalize` is available for explicit cleanup, but this
profile does not provide unloading: a plugin must restore its patches before
its code or callback storage can be released.

The builder generates exports into the output's private `.prx.objects` directory,
links an ELF, fixes imports and generates the PRX with the existing SDK utilities.
Each stage must succeed before replacing previous PRX/ELF/map outputs. It also
produces `.prx.map`; cleanup removes only those selected outputs and their private
objects. SDK files and other plugin outputs remain untouched. Full compilation
on each invocation avoids stale objects after manifest or flag changes.

For native-game hooks using injector's C++ frontend, add
`"PSP_GAME_ABI_COMPAT"` to `defines`. The builder treats f21/f23/f25/f27 as
caller-saved and reserves f28/f30. Typed `MakeCALL`, `MakeJMP` and inline hooks
then generate a module-owned callback boundary that preserves both SDK EABI
and native-game floating-point conventions. This adds no callback allocations.
Calls through integer addresses remain raw native stubs. C integrations can use
`psp_game_emit_callback` from `psp/game_abi.h` with their explicit overflow-stack
size. Caller-sensitive, integer-only C++ inline hooks may opt out through
`Options::preserve_game_callees`; they must not call floating-point SDK routines.

The legacy `vsmake.ps1` remains available for projects with their own SDK makefiles.

Run `python -B -m unittest discover -s plugins -p test_build.py -v` to verify real
C and C++ builds, Debug/Release defines, paths with spaces, failed-build preservation
and bounded clean.
