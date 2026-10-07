"""Compile real C/C++ PRXs, preserve outputs on failure, and bound cleanup."""
import json
import struct
from pathlib import Path
import subprocess
import tempfile
import unittest

BUILDER = Path(__file__).with_name('build-module.ps1')
EXPORTS = '''PSP_BEGIN_EXPORTS
PSP_EXPORT_START(syslib, 0, 0x8000)
PSP_EXPORT_FUNC(module_start)
PSP_EXPORT_VAR(module_info)
PSP_EXPORT_END
PSP_END_EXPORTS
'''


class ModuleBuild(unittest.TestCase):
    def test_minimal_cpp_runtime(self):
        with tempfile.TemporaryDirectory(prefix='psp cpp runtime ') as directory:
            root = Path(directory)
            (root / 'main.cpp').write_text(
                '#include <pspkernel.h>\n'
                'PSP_MODULE_INFO("MinimalCppProbe", 0, 1, 0);\n'
                'static volatile int constructed, destroyed;\n'
                'struct Owner { Owner() {++constructed;} ~Owner() {++destroyed;} };\n'
                'static Owner owner;\n'
                'extern "C" void __cxa_finalize(void*);\n'
                'extern "C" int module_start(SceSize, void*) {\n'
                ' if (constructed != 1 || destroyed) return -1;\n'
                ' __cxa_finalize(0); return destroyed == 1 ? sceKernelDelayThread(1) : -2;\n'
                '}\n')
            (root / 'exports.exp').write_text(EXPORTS)
            project = root / 'module.json'
            project.write_text(json.dumps(dict(sources=['main.cpp'], output='out/plugin.prx', exports='exports.exp')))
            result = subprocess.run(['powershell', '-NoProfile', '-ExecutionPolicy', 'Bypass', '-File',
                                     str(BUILDER), '-Project', str(project)], capture_output=True, text=True)
            self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
            # Check linkage as well as successful output: a minimal C++ PRX must
            # include the startup wrapper, constructor list, and bounded finalizer.
            map_text = (root / 'out/plugin.prx.map').read_text()
            for name in ('plugin_module_start', '__cxa_atexit', '__cxa_finalize', '__plugin_ctors_start'):
                self.assertIn(name, map_text)
            self.assertEqual((root / 'out/plugin.prx').read_bytes()[:7], b'\x7fELF\x01\x01\x01')

    def test_configuration_defines(self):
        for configuration in ('Release', 'Debug'):
            with self.subTest(configuration=configuration), tempfile.TemporaryDirectory(prefix='psp config ') as directory:
                root = Path(directory)
                expected = configuration == 'Debug'
                checks = ('#if !defined(DEBUG) || !defined(_DEBUG) || defined(NDEBUG)\n'
                          if expected else '#if defined(DEBUG) || defined(_DEBUG) || !defined(NDEBUG)\n')
                (root / 'main.c').write_text(
                    '#include <pspkernel.h>\n' + checks + '#error Wrong configuration\n#endif\n'
                    'PSP_MODULE_INFO("ConfigProbe", 0, 1, 0);\n'
                    'int module_start(SceSize n, void* p) {(void)n;(void)p;return sceKernelDelayThread(1);}\n')
                (root / 'exports.exp').write_text(EXPORTS)
                project = root / 'module.json'
                project.write_text(json.dumps(dict(sources=['main.c'], output='out/plugin.prx',
                                                  exports='exports.exp')))
                command = ['powershell', '-NoProfile', '-ExecutionPolicy', 'Bypass', '-File',
                           str(BUILDER), '-Project', str(project)]
                if expected:
                    command += ['-Configuration', configuration]
                result = subprocess.run(command, capture_output=True, text=True)
                self.assertEqual(result.returncode, 0, result.stdout + result.stderr)

    def test_c_cpp_spaces_failure_and_cleanup(self):
        for cpp in (False, True):
            with self.subTest(cpp=cpp), tempfile.TemporaryDirectory(prefix='psp module ') as directory:
                root = Path(directory)
                extension = 'cpp' if cpp else 'c'
                source = root / ('main.' + extension)
                text = '#include <pspkernel.h>\n#define PROBE_NAME "JsonProbe012345678901234567"\nPSP_MODULE_INFO(PROBE_NAME, 0, 1, 0);\n'
                if cpp:
                    text += '#include <string>\nstatic std::string probe("constructors");\nint main(int, char**) {return probe.size() == 12 ? 0 : 1;}\n'
                else:
                    text += 'int module_start(SceSize n, void* p) {(void)n;(void)p;return sceKernelDelayThread(1);}\n'
                source.write_text(text)
                (root / 'exports.exp').write_text(EXPORTS)
                manifest = dict(sources=[source.name], output='out/plugin.prx', exports='exports.exp',
                                startup='crt' if cpp else 'module_start', libraries=['-lm'])
                project = root / 'module.json'
                project.write_text(json.dumps(manifest))
                command = ['powershell', '-NoProfile', '-ExecutionPolicy', 'Bypass', '-File', str(BUILDER), '-Project', str(project)]
                result = subprocess.run(command, capture_output=True, text=True)
                self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
                outputs = [root / ('out/' + name) for name in ('plugin.prx', 'plugin.elf', 'plugin.prx.map')]
                previous = [path.read_bytes() for path in outputs]
                self.assertEqual(previous[0][:7], b'\x7fELF\x01\x01\x01')
                # C++ must retain the same module identity as C, including macro
                # expansion. Stringification used to produce "PROBE_NAME".
                elf = previous[1]
                start = struct.unpack_from('<I', elf, 32)[0]
                count, names_index = struct.unpack_from('<HH', elf, 48)
                sections = [struct.unpack_from('<10I', elf, start + i * 40) for i in range(count)]
                names = sections[names_index]
                for section in sections:
                    begin = names[4] + section[0]
                    name = elf[begin:elf.index(b'\0', begin)]
                    if name == b'.rodata.sceModuleInfo':
                        begin = section[4] + 4
                        self.assertEqual(elf[begin:begin + 28], b'JsonProbe012345678901234567\0')
                        break
                else:
                    self.fail('Missing module metadata')
                source.write_text(text + '\nthis is invalid source;\n')
                result = subprocess.run(command, capture_output=True, text=True)
                self.assertNotEqual(result.returncode, 0)
                self.assertEqual([path.read_bytes() for path in outputs], previous)
                source.write_text(text)
                (root / 'exports.exp').write_text('INVALID EXPORTS\n')
                result = subprocess.run(command, capture_output=True, text=True)
                self.assertNotEqual(result.returncode, 0)
                self.assertEqual([path.read_bytes() for path in outputs], previous)
                (root / 'exports.exp').write_text(EXPORTS)
                manifest['link_options'] = ['-lmissing_library']
                project.write_text(json.dumps(manifest))
                result = subprocess.run(command, capture_output=True, text=True)
                self.assertNotEqual(result.returncode, 0)
                self.assertEqual([path.read_bytes() for path in outputs], previous)
                self.assertFalse(list((root / 'out').glob('*.tmp')))
                keep = root / 'out/keep.txt'
                keep.write_text('preserve')
                result = subprocess.run(command + ['-Clean'], capture_output=True, text=True)
                self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
                self.assertTrue(all(not path.exists() for path in outputs))
                self.assertFalse((root / 'out/plugin.prx.objects').exists())
                self.assertEqual(keep.read_text(), 'preserve')


if __name__ == '__main__':
    unittest.main()
