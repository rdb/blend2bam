import argparse
import os
import sys
import tempfile


from .common import Settings
from .version import __version__
from . import blenderutils


def convert(settings, srcdir, src, dst):
    if settings.pipeline == 'gltf':
        from .blend2gltf import ConverterBlend2Gltf
        from .gltf2bam import ConverterGltf2Bam
        src2tmp = ConverterBlend2Gltf(settings)
        tmp2dst = ConverterGltf2Bam(settings)
        tmpext = '.gltf'
    elif settings.pipeline == 'gltf28':
        from .blend2gltf import ConverterBlend2Gltf28
        from .gltf2bam import ConverterGltf2Bam
        src2tmp = ConverterBlend2Gltf28(settings)
        tmp2dst = ConverterGltf2Bam(settings)
        tmpext = '.gltf'
    elif settings.pipeline == 'egg':
        from .blend2egg import ConverterBlend2Egg
        from .egg2bam import ConverterEgg2Bam
        src2tmp = ConverterBlend2Egg(settings)
        tmp2dst = ConverterEgg2Bam(settings)
        tmpext = '.egg'
    else:
        raise RuntimeError('Unknown pipeline: {}'.format(settings.pipeline))

    for src_element in src:
        if not os.path.exists(src_element):
            print('Source ({}) does not exist'.format(src_element))
            sys.exit(1)

        if len(src) > 1 and not os.path.isfile(src_element):
            print('Source ({}) is not a file'.format(src_element))
            sys.exit(1)

        if len(src) == 1 and not (os.path.isfile(src_element) or os.path.isdir(src_element)):
            print('Source ({}) must be a file or a directory'.format(src))
            sys.exit(1)

    src_is_dir = os.path.isdir(src[0])
    dst_is_dir = not os.path.splitext(dst)[1]

    if dst_is_dir and not dst.endswith(os.sep):
        dst = dst + os.sep

    files_to_convert = []
    if src_is_dir:
        srcdir = src[0]
        for root, _, files in os.walk(srcdir):
            files_to_convert += [
                os.path.join(root, i)
                for i in files
                if i.endswith('.blend')
            ]
    else:
        files_to_convert = [os.path.abspath(i) for i in src]

    is_batch = len(files_to_convert) > 1 or dst_is_dir

    if is_batch and not dst_is_dir:
        print('Destination must be a directory if the source is a directory or multiple files')

    if is_batch:
        # Batch conversion
        tmpfiles = [i.replace(srcdir, dst).replace('.blend', tmpext) for i in files_to_convert]
        try:
            src2tmp.convert_batch(srcdir, dst, files_to_convert)
            tmp2dst.convert_batch(dst, dst, tmpfiles)
        except: #pylint: disable=bare-except
            import traceback
            traceback.print_exc()
            print('Failed to convert all files', file=sys.stderr)
        finally:
            _ = [
                os.remove(i)
                for i in tmpfiles
                if os.path.exists(i)
            ]
    else:
        # Single file conversion
        srcfile = files_to_convert[0]
        if dst_is_dir:
            # Destination is a directory, add a filename
            dst = os.path.join(dst, os.path.basename(srcfile.replace('blend', 'bam')))

        tmpfile = tempfile.NamedTemporaryFile(delete=False)
        tmpfile.close()
        try:
            src2tmp.convert_single(srcfile, tmpfile.name)
            tmp2dst.convert_single(tmpfile.name, dst)
        except: #pylint: disable=bare-except
            import traceback
            traceback.print_exc()
            print('Failed to convert all file', file=sys.stderr)
        finally:
            if os.path.exists(tmpfile.name):
                os.remove(tmpfile.name)

def main():
    parser = argparse.ArgumentParser(
        description='CLI tool to convert Blender blend files to Panda3D BAM files'
    )

    parser.add_argument(
        '--version',
        action='version',
        version='%(prog)s {version}'.format(version=__version__),
    )

    parser.add_argument('src', nargs='+', type=str, help='source path')
    parser.add_argument('dst', type=str, help='destination path')

    parser.add_argument(
        '-m', '--material-mode',
        choices=[
            'legacy',
            'pbr',
        ],
        default='legacy',
        help='control how materials are exported'
    )

    parser.add_argument(
        '--physics-engine',
        choices=[
            'builtin',
            'bullet',
        ],
        default='builtin',
        help='the physics engine to build collision solids for'
    )

    parser.add_argument(
        '--srcdir',
        default=None,
        help='a common source directory to use when specifying multiple source files'
    )

    parser.add_argument(
        '--blender-dir',
        default='',
        help='directory that contains the blender binary'
    )

    parser.add_argument(
        '--append-ext',
        action='store_true',
        help='append extension on the destination instead of replacing it (batch mode only)'
    )

    parser.add_argument(
        '--pipeline',
        choices=[
            'gltf',
            'gltf28',
            'egg',
        ],
        default='gltf',
        help='the backend pipeline used to convert files'
    )

    parser.add_argument(
        '--no-srgb',
        action='store_true',
        help='do not load textures as sRGB textures (only for glTF pipelines)'
    )

    parser.add_argument(
        '--textures',
        choices=[
            'ref',
            'copy',
            'embed',
        ],
        default='ref',
        help='how to handle external textures'
    )

    args = parser.parse_args()

    src = [os.path.abspath(i) for i in args.src]
    if args.srcdir:
        srcdir = args.srcdir
    else:
        srcdir = os.path.dirname(src[0]) if len(src) == 1 else os.path.commonpath(src)
    dst = os.path.abspath(args.dst)

    if not blenderutils.blender_exists(args.blender_dir):
        print(
            'Blender not found! Try adding Blender to the system PATH or using '
            '--blender-dir to point to its location'
        )
        sys.exit(1)

    use_gltf28 = blenderutils.is_blender_28(args.blender_dir)
    if use_gltf28 and args.pipeline != 'gltf28':
        print('Blender version is 2.8+, forcing gltf28 pipeline')
        args.pipeline = 'gltf28'
    elif not use_gltf28 and args.pipeline == 'gltf28':
        print('Blender version is not 2.8+ but gltf28 pipeline was selected, forcing to gltf')
        args.pipeline = 'gltf'

    settings = Settings(
        material_mode=args.material_mode,
        physics_engine=args.physics_engine,
        blender_dir=args.blender_dir,
        append_ext=args.append_ext,
        pipeline=args.pipeline,
        no_srgb=args.no_srgb,
        textures=args.textures,
    )

    convert(settings, srcdir, src, dst)
