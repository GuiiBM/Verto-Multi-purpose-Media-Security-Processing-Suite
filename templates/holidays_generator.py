import requests
from datetime import datetime
import json

def get_brazilian_holidays(year):
    """
    Busca feriados brasileiros via API pública e calcula feriados móveis
    """
    holidays = []
    
    # Feriados fixos
    fixed_holidays = [
        {'date': f'{year}-01-01', 'name': 'Confraternização Universal'},
        {'date': f'{year}-04-21', 'name': 'Tiradentes'},
        {'date': f'{year}-05-01', 'name': 'Dia do Trabalho'},
        {'date': f'{year}-09-07', 'name': 'Independência do Brasil'},
        {'date': f'{year}-10-12', 'name': 'Nossa Senhora Aparecida'},
        {'date': f'{year}-11-02', 'name': 'Finados'},
        {'date': f'{year}-11-15', 'name': 'Proclamação da República'},
        {'date': f'{year}-11-20', 'name': 'Consciência Negra'},
        {'date': f'{year}-12-25', 'name': 'Natal'}
    ]
    
    # Calcular Páscoa (algoritmo de Meeus/Jones/Butcher)
    a = year % 19
    b = year // 100
    c = year % 100
    d = b // 4
    e = b % 4
    f = (b + 8) // 25
    g = (b - f + 1) // 3
    h = (19 * a + b - d - g + 15) % 30
    i = c // 4
    k = c % 4
    l = (32 + 2 * e + 2 * i - h - k) % 7
    m = (a + 11 * h + 22 * l) // 451
    month = (h + l - 7 * m + 114) // 31
    day = ((h + l - 7 * m + 114) % 31) + 1
    
    easter = datetime(year, month, day)
    
    # Feriados móveis baseados na Páscoa
    from datetime import timedelta
    
    carnaval = easter - timedelta(days=48)
    carnaval_terca = easter - timedelta(days=47)
    sexta_santa = easter - timedelta(days=2)
    corpus_christi = easter + timedelta(days=60)
    
    mobile_holidays = [
        {'date': carnaval.strftime('%Y-%m-%d'), 'name': 'Carnaval'},
        {'date': carnaval_terca.strftime('%Y-%m-%d'), 'name': 'Carnaval'},
        {'date': sexta_santa.strftime('%Y-%m-%d'), 'name': 'Sexta-feira Santa'},
        {'date': corpus_christi.strftime('%Y-%m-%d'), 'name': 'Corpus Christi'}
    ]
    
    holidays = fixed_holidays + mobile_holidays
    
    # Ordenar por data
    holidays.sort(key=lambda x: x['date'])
    
    return holidays

def get_holidays_cache(start_year=2024, end_year=2030):
    """
    Gera cache de feriados para múltiplos anos
    """
    cache = {}
    for year in range(start_year, end_year + 1):
        cache[str(year)] = get_brazilian_holidays(year)
    return cache

if __name__ == '__main__':
    # Gerar cache
    cache = get_holidays_cache(2024, 2030)
    print(json.dumps(cache, indent=2, ensure_ascii=False))
