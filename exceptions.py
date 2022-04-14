class Non200ResponseException(Exception):
    def __init__(self, resp):
        self.message = f'Получен ответ {resp} от API'

    def __str__(self):
        return self.message

