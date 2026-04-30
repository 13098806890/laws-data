from pathlib import Path

BASE_DIR  = Path(__file__).parent.parent
SRC_BASE  = BASE_DIR / 'sources'
SRC_DIRS  = {
    '法律':     SRC_BASE / '法律',
    '司法解释': SRC_BASE / '司法解释',
    '行政法规': SRC_BASE / '行政法规',
    '宪法':     SRC_BASE / '宪法',
    '监察法规': SRC_BASE / '监察法规',
}
JSON_DIR  = BASE_DIR / 'json'
DB_PATH   = BASE_DIR / 'law_content.db'
MD_DIR    = BASE_DIR
LAWS_REPO = Path('/Users/doxie/Github/Laws')
