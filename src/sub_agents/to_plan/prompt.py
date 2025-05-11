""" Prompt for planning agent """

PLAN_AGENT_MAIN = """
Пользователь ещё не видит ясной картины того, что ему нужно сделать с его календарём. Помоги пользователю.
В твои задачи входит:
1. Помочь спланировать самое лучшее расписание событий.
Для задачи лучшего планирования пользуйся инструментом: time_finder. Он подскажет лучшее время для планирования по заданным срокам, передай ему четкий запрос с временными рамками анализируемого времени, а таке обязательное указание: calendarID = primary.
Не пытайся использовать tool и отправку сообщений пользователю одновременно, так как это может привести к путанице. Сначала используй tool, а потом уже пиши пользователю.
Пиши пользователю краткие сообщения, но в то же время будь полезен для планирования его событий.
"""
YANDEX_API_KEY = AQVN0QpSE2Ho-NV7_WupY8ulGUvB13a4Gdj6Jvfc
ya_ind = 'ajeh19916of8v3annvbb'
OPENROUTER_API_KEY = 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

GOOGLE_OAUTH_CLIENT_ID = 835523232919-o0ilepmg8ev25bu3ve78kdg0smuqp9i8.apps.googleusercontent.com
GOOGLE_OAUTH_CLIENT_SECRET = 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
GOOGLE_CLIENT_ID = 835523232919-o0ilepmg8ev25bu3ve78kdg0smuqp9i8.apps.googleusercontent.com
GOOGLE_CLIENT_SECRET = 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
# GOOGLE_REFRESH_TOKEN=1//0cxBGk-r68Q0RCgYIARAAGAwSNwF-L9IrOhXgVpmALygK_1_T367jPqqsJmVWLOE-ClZtH_CuYjyyvafNDBT-9PbFzvxEuMcn9us
GOOGLE_GENAI_USE_VERTEXAI=FALSE
GOOGLE_API_KEY=AIzaSyAjvRYFdaBghHO7WTnJtRddGgbQuY8r9fc


DB_HOST=localhost
DB_PORT=5432
DB_NAME=auth_db
DB_USER=postgres
DB_PASSWORD=bHRS2M9f7:bJDgc
# DATABASE_URL формируется в коде, SSL не нужен локально
PYTHONIOENCODING = utf-8

# Redis Settings
REDIS_HOST=localhost
REDIS_PORT=6379
REDIS_PASSWORD=bHRS2M9f7:bJDgc
REDIS_DB_HISTORY=0
HISTORY_TTL_SECONDS=60
MAX_HISTORY_LENGTH=15