"""Compile real C/C++ PRXs, preserve outputs on failure, and bound cleanup."""
import json
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
    def test_c_cpp_spaces_failure_and_cleanup(self):
        for cpp in (False, True):
            with self.subTest(cpp=cpp), tempfile.TemporaryDirectory(prefix='psp module ') as directory:
                root = Path(directory)
                extension = 'cpp' if cpp else 'c'
                source = root / ('main.' + extension)
                text = '#include <pspkernel.h>\nPSP_MODULE_INFO("JsonProbe", 0, 1, 0);\n'
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
