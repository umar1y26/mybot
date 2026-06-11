from PIL import Image
from PIL.ExifTags import TAGS


def check_photo(img_path):
    try:
        img = Image.open(img_path)
        exif = img._getexif()

        if exif:
            print(f"--- Метаданные файла {img_path} ---")
            for tag, value in exif.items():
                tag_name = TAGS.get(tag, tag)
                print(f"{tag_name}: {value}")
        else:
            print("В этом фото нет скрытых данных (EXIF).")

    except Exception as e:
        print(f"Ошибка: {e}")


# Запуск функции для твоего фото
check_photo('test.jpg')
