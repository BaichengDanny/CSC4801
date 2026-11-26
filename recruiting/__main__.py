"""Run the local application with a production WSGI server."""
import os

from waitress import serve

from . import create_app


def main():
    app = create_app()
    serve(app, host=os.environ.get('HOST', '127.0.0.1'), port=int(os.environ.get('PORT', '8080')))


if __name__ == '__main__':
    main()
