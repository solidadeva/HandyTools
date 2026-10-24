"""Real HEIC regression: grid assembly, primary selection, paths and cleanup."""
import tempfile
from pathlib import Path
from unittest.mock import patch
from PIL import Image, ImageDraw
import pillow_heif
from engine import Conversion, Cancelled


def main():
    with tempfile.TemporaryDirectory() as temp:
        folder = Path(temp) / 'عکس فارسی with spaces'
        folder.mkdir()
        image = Image.new('RGB', (1536, 1024))
        draw = ImageDraw.Draw(image)
        colors = [(230, 20, 20), (20, 220, 20), (20, 20, 230), (230, 220, 20)]
        for box, color in zip([(0, 0, 767, 511), (768, 0, 1535, 511),
                               (0, 512, 767, 1023), (768, 512, 1535, 1023)], colors):
            draw.rectangle(box, fill=color)
        source = folder / 'تصویر.HEIC'
        heif = pillow_heif.from_pillow(Image.new('RGB', (64, 64), 'magenta'))
        heif.add_from_pillow(image)
        heif.save(source, quality=95, primary_index=1, tile_size=512)
        original = source.read_bytes()
        assert b'grid' in original, 'fixture must contain a HEIF grid'
        assert pillow_heif.open_heif(source).size == image.size
        for fmt in ('JPG', 'PNG', 'WEBP'):
            updates = []
            result = Conversion().run(source, folder, fmt, updates.append)
            assert result.name.startswith('تصویر_converted')
            with Image.open(result) as output:
                assert output.size == image.size, (fmt, output.size)
                for point, expected in zip([(100, 100), (1400, 100), (100, 900), (1400, 900)], colors):
                    actual = output.convert('RGB').getpixel(point)
                    assert max(abs(a-b) for a,b in zip(actual, expected)) < 25, (fmt, point, actual)
            assert updates[-1] == 100
            print('PASS full tiled primary HEIC ->', fmt)
        assert source.read_bytes() == original
        prior = set(folder.iterdir())
        job = Conversion()
        job.cancel()
        try:
            job.run(source, folder, 'JPG')
        except Cancelled:
            pass
        else:
            raise AssertionError('expected cancel')
        assert set(folder.iterdir()) == prior
        # Cancel after decoding: no reserved output or decoded temporary left.
        job = Conversion()
        real_save = Image.Image.save
        decoded_paths = []
        def save_then_cancel(self, path, *args, **kwargs):
            real_save(self, path, *args, **kwargs)
            decoded_paths.append(Path(path))
            job.cancel()
        with patch.object(Image.Image, 'save', save_then_cancel):
            try:
                job.run(source, folder, 'JPG')
            except Cancelled:
                pass
            else:
                raise AssertionError('expected cancel after decode')
        assert decoded_paths and all(not p.exists() for p in decoded_paths)
        assert set(folder.iterdir()) == prior
        broken = folder / 'broken.heic'
        broken.write_bytes(b'invalid heic')
        prior = set(folder.iterdir())
        try:
            Conversion().run(broken, folder, 'JPG')
        except RuntimeError as exc:
            assert 'complete HEIC' in str(exc)
        else:
            raise AssertionError('expected invalid image failure')
        assert set(folder.iterdir()) == prior
        print('PASS source preserved, cancellation and invalid HEIC cleanup')

import unittest


class HeicRegression(unittest.TestCase):
    def test_primary_tiled_image_and_cleanup(self):
        main()


if __name__ == '__main__':
    unittest.main()
