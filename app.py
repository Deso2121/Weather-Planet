from datetime import datetime
from datetime import timedelta
from datetime import date
from json.decoder import JSONDecodeError
import json
import requests
import io
import base64
import matplotlib.dates as mdates
import matplotlib.pyplot as plt
import time
from flask import Flask, Response, render_template, request
from wtforms import Form, StringField

app = Flask(__name__)
app.config['DEBUG'] = True


class SearchForm(Form):
    autocomp = StringField('Location:', id='city_autocomplete')


@app.route('/_autocomplete', methods=['GET'])
def autocomplete():
    with open('data/city.list.json', encoding="utf-8") as file:
        data = json.load(file)
    place_list = []
    for line in data:
        place_list.append(line['name'])
    place_list = list(dict.fromkeys(place_list))
    return Response(json.dumps(place_list), mimetype='application/json')


@app.route('/', methods=['GET', 'POST'])
def index():
    # Pole odpowiadające polu tekstowemu Lokalizacja przekazywanemu ze strony
    form = SearchForm(request.form)
    # Stworzony obiekt klasy TempData, wykorzystywany do odczytania pliku temp_data.json
    temp_class = TempData()
    temp_data = temp_class.temp_data

    # Nazwy lokacji odczytywane są z pliku city.list.json, z kolumny ['name']
    location_names = temp_class.read_temp('data/city.list.json')
    location_names = [x['name'] for x in location_names]
    # Jako adres img wykresu podany jest początkowo adres ikony teleskopu - nie stworzony jeszcze wykresu
    plot = "/static/img/telescope.svg"
    location = ''
    # Wywołanie funkcji zwracających 5 poprzednich dni w formie unix timestamps
    five_previous_days_unix = convert_dates_to_unix(get_5_previous_days())
    historic_urls = []
    # Szkic obiektu weather, wyświetlany w przypadku gdy nie została wyszukana żadna lokacja
    weather = {
        'city': "",
        'temperature': 0,
        'temperature_min': 0,
        'temperature_max': 0,
        'pressure': 0,
        'humidity': 0,
        'wind_speed': 0,
        'description': "",
        'icon': "01d",
        'temp1': 0,
        'temp2': 0,
        'temp3': 0,
        'temp4': 0,
        'temp5': 0,
        'day1': (date.today() + timedelta(days=1)).strftime("%d.%m"),
        'day2': (date.today() + timedelta(days=2)).strftime("%d.%m"),
        'day3': (date.today() + timedelta(days=3)).strftime("%d.%m"),
        'day4': (date.today() + timedelta(days=4)).strftime("%d.%m"),
        'day5': (date.today() + timedelta(days=5)).strftime("%d.%m")
    }

    # Ta pętla wykonywana jest gdy metoda zapytana to POST, tzn. gdy strona wyśle informację POST aplikacji
    if request.method == 'POST':
        # Lokacja dla której będą tworzone zapytania do API jest wartością wpisaną w pole "autocomplete"
        location = request.form['autocomp']
        # Jeśli tej lokacji nie ma jeszcze w naszych danych, zostaje tworzony dla niej pusty słownik
        if location not in temp_data:
            temp_data[location] = dict()
        # Pętla wykonywana gdy lokacja znajduje się w dostępnych nazwach,
        # tj. gdy możemy złożyć zapytanie o nią do API
        if location in location_names:
            # Pierwszy url odpowiada zapytaniu o aktualną pogodę, drugi prognozie. Podawany jest parametr lokacji
            url = \
                'http://api.openweathermap.org/data/2.5/weather?q={}' \
                '&units=metric&appid=db9290ffa2c3ea5ba13b50228182ff33'.format(location)
            url_2 = \
                'http://api.openweathermap.org/data/2.5/forecast?q={}' \
                '&units=metric&appid=db9290ffa2c3ea5ba13b50228182ff33'.format(location)
            # Response to dane otrzymywane od API zapisane w formacie json
            response = requests.get(url.format(location)).json()
            response_2 = requests.get(url_2.format(location)).json()
            # Długość i szerokość geograficzna wybranej lokacji - call historyczny
            # można wykonać tylko na tych wartościach, nie przyjmuje nazwy
            lon, lat = response['coord']['lon'], response['coord']['lat']
            # Za pomocą pętli tworzymy url dla każdego z 5 poprzednich dni - osobny call dla każdego dnia
            for x in range(1, 6):
                historic_urls.append(
                    'https://api.openweathermap.org/data/2.5/'
                    'onecall/timemachine?lat={}&lon={}&units=metric&dt={}&appid={}'
                        .format(lat, lon, five_previous_days_unix[5 - x], 'db9290ffa2c3ea5ba13b50228182ff33'))
            # Tworzymy array i dodajemy do niego wszystkie 5 odpowiedzi API (response)
            historic_response = []
            for x in historic_urls:
                historic_response.append(requests.get(x).json())
            # Historic temp to słownik z datami w formacie "%Y-%m-%d" oraz temperaturą
            historic_temp = dict()
            for x in historic_response:
                historic_temp[datetime.fromtimestamp(x['current']['dt']).strftime('%Y-%m-%d')] = x['current']['temp']
            # Iterujemy po stworzonym słowniku i dopisujemy dane do obiektu temp_data, który jest zapisywany
            # w pliku json
            for x, y in historic_temp.items():
                temp_data[location][x] = y
            temp_class.write_temp(temp_data)

            # Tworzymy wykres
            plot = build_plot(temp_data, location)
            # Zapisujemy w pojedynczym obiekcie wszystkie wyświetlane przez stronę dane; przekazujemy jej ten obiekt
            weather = {
                'city': location,
                'temperature': response['main']['temp'],
                'temperature_min': response['main']['temp_min'],
                'temperature_max': response['main']['temp_max'],
                'pressure': response['main']['pressure'],
                'humidity': response['main']['humidity'],
                'wind_speed': response['wind']['speed'],
                'description': response['weather'][0]['description'],
                'icon': response['weather'][0]['icon'],
                'temp1': response_2['list'][0]['main']['temp'],
                'temp2': response_2['list'][1]['main']['temp'],
                'temp3': response_2['list'][2]['main']['temp'],
                'temp4': response_2['list'][3]['main']['temp'],
                'temp5': response_2['list'][4]['main']['temp'],
                'day1': (date.today() + timedelta(days=1)).strftime("%d.%m"),
                'day2': (date.today() + timedelta(days=2)).strftime("%d.%m"),
                'day3': (date.today() + timedelta(days=3)).strftime("%d.%m"),
                'day4': (date.today() + timedelta(days=4)).strftime("%d.%m"),
                'day5': (date.today() + timedelta(days=5)).strftime("%d.%m")
            }
    # Na końcu zwracamy obiekt render_template, który jest odczytaniem szablonu strony wraz ze zmiennymi
    return render_template("weather.html", form=form, weather=weather, plot=plot)


# Funkcja tworząca wykres
def build_plot(temp_data, location):
    # img posłuży nam konwersji stworzonego w matplotlib wykresu na kod url
    img = io.BytesIO()
    # Filtrujemy nasze dane temp_data i wyciągamy dane dla wybranej przez użytkownika lokacji
    current_date_temp = get_location_temp(temp_data, location)

    # Czyścimy wykres za każdym razem, aby uniknąć nakładania się na siebie kilku wykresów
    plt.clf()
    ax = plt.gca()
    fig = plt.gcf()
    # Daty i wartości temperatur to odpowiednio klucze i wartości stworzonego wcześniej słownika
    plt_date = [x for x in current_date_temp.keys()]
    y = [x for x in current_date_temp.values()]
    # Zamieniamy daty na format dat wykorzystywany w matplotlibie
    dates_num = [mdates.date2num(datetime.strptime(x, "%Y-%m-%d")) for x in plt_date]
    # Tworzymy obiekty służące odpowiedniemu sformatowaniu osi na wykresie
    locator = mdates.AutoDateLocator(minticks=3, maxticks=7)
    formatter = mdates.ConciseDateFormatter(locator)
    ax.xaxis.set_major_locator(locator)
    ax.xaxis.set_major_formatter(formatter)
    plt.plot(dates_num, y)
    plt.ylabel("Temperature at 12p.m.")

    # Zapisujemy wykres w obiekcie img pod formatem png, następnie kodujemy go; kod zwracany jest przez funkcję
    plt.savefig(img, format='png')
    img.seek(0)
    plot_url = base64.b64encode(img.getvalue()).decode()
    return "data:image/png;base64,{}".format(plot_url)


# Funkcja wycinająca fragment danych odpowiadający wybranej lokacji
def get_location_temp(temp_data, location):
    location_temp = temp_data[location]
    return location_temp


# Funkcja zwracająca daty odpowiadające 5 poprzednim dniom
def get_5_previous_days():
    dates = []
    today = datetime.now()
    today_12 = datetime.replace(today, hour=12, minute=0, second=0)
    for x in range(1, 6):
        dates.append(today_12 - timedelta(days=x))
    return dates


# Funkcja zamieniająca podane daty na daty w formacie UNIX
def convert_dates_to_unix(dates):
    dates_unix = [int(time.mktime(x.timetuple())) for x in dates]
    return dates_unix


# Klasa odpowiadająca za odczytywanie, przechowywanie oraz zapis naszych danych
class TempData:

    def __init__(self):
        self.temp_data = self.read_temp('data/temp_data.json')

    def read_temp(self, data):
        with open(data, encoding="utf-8") as file:
            try:
                temp_data = json.load(file)
            except JSONDecodeError:
                temp_data = dict()
        return temp_data

    def write_temp(self, temp_data):
        with open('data/temp_data.json', 'w', encoding='utf-8') as f:
            json.dump(temp_data, f, indent=2)


if __name__ == '__main__':
    app.run()
