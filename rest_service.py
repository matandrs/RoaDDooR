from flask import Flask, request, jsonify
import googlemaps
import mysql.connector
import configparser
import os
import openai
import json

app = Flask(__name__)

config = configparser.ConfigParser()
config.read('credentials.props')

openai_key = config['DEFAULT']['OPENAI_KEY']
gmaps_key = config['DEFAULT']['GOOGLEMAPS_KEY']

usuariodb = config['BBDD']['USER']
passworddb = config['BBDD']['PASSWORD']

openai.api_key = openai_key

# Configura tus credenciales de Google Maps API
gmaps = googlemaps.Client(key=gmaps_key)

# Configura la conexión a la base de datos MySQL
db_config = {
    'user': usuariodb,
    'password': passworddb,
    'host': '127.0.0.1',
    'database': 'roaddoor',
}

def get_pueblos():
    connection = mysql.connector.connect(**db_config)
    cursor = connection.cursor()

    query = "SELECT * FROM pueblo"
    cursor.execute(query)

    pueblos = []
    for row in cursor.fetchall():
        pueblos.append({
            'id': row[0],
            'nombre': row[1],
            'descripcion': row[2],
            'latitud': row[3],
            'longitud': row[4],
            'servicios': row[5],
            'valoracion': row[6]
        })

    cursor.close()
    connection.close()

    return pueblos


def ponderar_pueblos_gpt(pueblos, origen, preferencias):
    prompt = f"Por favor, clasifica los siguientes pueblos en función de su cercanía al origen '{origen}', las preferencias del usuario {preferencias} y las valoraciones de otros usuarios:\n\n"
    for i, pueblo in enumerate(pueblos):
        prompt += f"{i + 1}. {pueblo['nombre']} (Cercanía: {pueblo['distancia']} metros, Preferencias coincidentes: {pueblo['preferencias_coincidentes']}, Valoración: {pueblo['valoracion']} estrellas)\n"

    prompt += "\nOrdena los pueblos de mejor a peor opción, devolviendo los resultados en un array de JSON que contenga cada pueblo "
    prompt += "estrictamente en el siguiente formato, sin responder nada más que el JSON:\n"
    prompt += "{'nombre': 'Pueblo 1', 'latitud': 40.123, 'longitud': -3.456, 'distancia': 1234, 'preferencias_coincidentes': 2, 'valoracion': 4.5}\n"

    response = openai.ChatCompletion.create(model="gpt-3.5-turbo",messages=[
        {"role": "system", "content": "You are a helpful assistant."},
        {"role": "user", "content": prompt},
    ], max_tokens=1500, temperature=0)

    ranked_pueblos = json.loads(response['choices'][0]['message']['content'])

    return ranked_pueblos


@app.route('/ruta', methods=['POST'])
def calcular_ruta():
    data = request.get_json()

    origen = data['origen']
    destino = data['destino']
    distancia_desviacion = data['distancia_desviacion']
    preferencias = data['preferencias']
    num_paradas = data['num_paradas']

    # Calcular la ruta base
    ruta_base = gmaps.directions(origen, destino)

    # Obtener pueblos de la base de datos
    pueblos = get_pueblos()

    # Filtrar pueblos en función de la distancia de desviación y las preferencias
    pueblos_cercanos = []
    for pueblo in pueblos:
        distancia = gmaps.distance_matrix(origen, (pueblo['latitud'], pueblo['longitud']))
        distancia = distancia['rows'][0]['elements'][0]['distance']['value']

        preferencias_coincidentes = [pref for pref in preferencias if pref in pueblo['servicios']]
    

        if distancia <= distancia_desviacion:
            pueblos_cercanos.append({
                'nombre': pueblo['nombre'],
                'latitud': pueblo['latitud'],
                'longitud': pueblo['longitud'],
                'distancia': distancia,
                'preferencias_coincidentes': len(preferencias_coincidentes),
                'valoracion': pueblo['valoracion']
            })

    # Ordenar pueblos usando GPT de OpenAI
    pueblos_ponderados = ponderar_pueblos_gpt(pueblos_cercanos, origen, preferencias)

    # Seleccionar el número de paradas especificado por el usuario
    pueblos_seleccionados = pueblos_ponderados[:num_paradas]

    # Añadir pueblos a la ruta
    waypoints = [{'lat': pueblo['latitud'], 'lng': pueblo['longitud']} for pueblo in pueblos_seleccionados]
    ruta_final = gmaps.directions(origen, destino, waypoints=waypoints, optimize_waypoints=True)

    return jsonify({"ruta": ruta_final, "pueblos_sugeridos": pueblos_ponderados[:10]})

if __name__ == '__main__':
    app.run(debug=True)