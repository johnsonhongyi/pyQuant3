# -*- mode: python ; coding: utf-8 -*-

block_cipher = None

a = Analysis(
    ['异动联动.py'],             # 你的主程序文件
    pathex=[],               # 你的项目路径
    binaries=[],
    datas=[],
    hiddenimports=[],
    hookspath=[],
    excludes=[
        # 大型科学计算和数据分析库（你不需要的）
        'matplotlib', 'seaborn', 'scipy', 'sklearn', 'numba', 'sympy', 'statsmodels',
        'pytz', 'dateutil', 'pytz_deprecation_shim', 'tzdata', 'tzlocal',
        
        # Jupyter / IPython 相关
        'jupyter', 'notebook', 'ipython', 'ipykernel', 'ipywidgets', 'jupyterlab',
        'nbconvert', 'nbformat', 'nbclient', 'jupyter_client', 'jupyter_core',
        'qtconsole', 'jupyterlab_code_formatter', 'jupyterlab_widgets', 'lckr_jupyterlab_variableinspector',
        
        # Web / HTTP / API 大包（你不需要的）
        'fastapi', 'starlette', 'uvicorn', 'requests_cache', 'aiohttp', 'tweepy', 'boto3', 'botocore',
        'scrapy', 'parsel', 'twisted', 'twisted_iocpsupport', 'gevent', 'gevent_websocket',
        'flask', 'werkzeug', 'gunicorn', 'hyperlink', 'cffi', 'cryptography', 'paramiko', 'pyasn1', 'pyasn1_modules',
        'asyncio', 'anyio', 'httpx', 'httpcore', 'sniffio', 'h11',
        
        # 数据可视化
        'plotly', 'cufflinks', 'bokeh', 'datashader', 'holoviews', 'hvplot', 'panel', 'colorcet', 'colorlover',
        'pyqtgraph', 'PyQt6', 'PyQt6_Qt6', 'PyQt6_sip', 'qdarkstyle', 'qtawesome', 'qtpy',
        
        # 开发工具 / 检查 / 格式化
        'autopep8', 'black', 'yapf', 'flake8', 'pylint', 'rope', 'jedi', 'mccabe', 'pycodestyle', 'pyflakes', 'isort', 'mypy_extensions',
        'pytest', 'mock', 'testpath', 'coverage', 'tox', 'pip_search', 'pip_autoremove',
        
        # 文档生成 / Sphinx
        'sphinx', 'sphinxcontrib_applehelp', 'sphinxcontrib_devhelp', 'sphinxcontrib_htmlhelp', 
        'sphinxcontrib_jsmath', 'sphinxcontrib_qthelp', 'sphinxcontrib_serializinghtml', 'recommonmark', 'numpydoc',
        
        # 其他不需要的杂项
        'tkinter', 'PIL', 'pillow', 'imageio', 'imagesize', 'imagecodecs', 'fonttools', 'matplotlib_inline', 
        'pygments', 'markdown', 'markdown_it_py', 'html5lib', 'cssselect', 'tinycss', 'beautifulsoup4', 'bs4',
        'pyquery', 'lxml', 'xpath', 'openpyxl', 'XlsxWriter', 'xlrd', 'xlwings', 'tables', 'xlsxwriter', 'pandas_ta',
        'numexpr', 'bottleneck', 'threadpoolctl', 'daal4py', 'mkl_service', 'mkl_fft', 'mkl_random',
        'scikit_learn_intelex', 'scikit_learn', 'sklearn', 'joblib', 'pywavelets', 'cv2', 'opencv_python',
        'gensim', 'nltk', 'textdistance', 'snowballstemmer', 'wordcloud', 'pytesseract', 'pyttsx3', 'pygame'
    ],
    noarchive=False
)

pyz = PYZ(a.pure, a.zipped_data,
          cipher=block_cipher)

exe = EXE(
    pyz,
    a.scripts,
    [],
    exclude_binaries=True,
    name='异动联动',
    debug=False,
    bootloader_ignore_signals=False,
    strip=True,
    upx=True,            
    console=True         
)

coll = COLLECT(
    exe,
    a.binaries,
    a.zipfiles,
    a.datas,
    strip=False,
    upx=True,
    upx_exclude=[],
    name='my_app'
)
