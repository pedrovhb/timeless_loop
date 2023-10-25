format:
    poetry run black .
    poetry run usort format .


build:
    poetry build

release bump:
    poetry version {{ bump }}
    poetry publish --build --username $PYPI_API_USERNAME --password $PYPI_API_PASSWORD
