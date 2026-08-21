"""Create the repository's deterministic HACS brand icon."""

from pathlib import Path

from PIL import Image, ImageDraw


def main() -> None:
    size = 512
    image = Image.new("RGBA", (size, size), (12, 25, 45, 255))
    draw = ImageDraw.Draw(image)
    draw.ellipse((28, 28, size - 28, size - 28), fill=(24, 103, 192, 255))
    draw.rounded_rectangle((94, 214, 418, 344), radius=48, fill=(240, 247, 255, 255))
    draw.polygon(
        ((153, 214), (202, 153), (325, 153), (372, 214)),
        fill=(240, 247, 255, 255),
    )
    draw.polygon(
        ((215, 174), (310, 174), (340, 214), (183, 214)),
        fill=(24, 103, 192, 255),
    )
    draw.ellipse((137, 306, 207, 376), fill=(12, 25, 45, 255))
    draw.ellipse((305, 306, 375, 376), fill=(12, 25, 45, 255))
    draw.ellipse((152, 321, 192, 361), fill=(180, 212, 245, 255))
    draw.ellipse((320, 321, 360, 361), fill=(180, 212, 245, 255))
    output = Path(__file__).resolve().parents[1] / "brand" / "icon.png"
    output.parent.mkdir(parents=True, exist_ok=True)
    image.save(output, format="PNG", optimize=True)


if __name__ == "__main__":
    main()
