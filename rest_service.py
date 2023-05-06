from flask import Flask, request, jsonify
import googlemaps
import mysql.connector

app = Flask(__name__)

# Configura tus credenciales de Google Maps API
gmaps = googlemaps.Client(key='YOUR_GOOGLE_MAPS_API_KEY')

# Configura la conexión a la base de datos MySQL
db_config = {
    'user': 'usuario',
    'password': 'contraseña',
    'host': 'ip_del_servidor',
    'database': 'base_de_datos',
}

def get_pueblos():
    connection = mysql.connector.connect(**db_config)
    cursor = connection.cursor()

    query = "SELECT * FROM pueblos"
    cursor.execute(query)

    pueblos = []
    for row in cursor.fetchall():
        pueblos.append({
            'id': row[0],
            'nombre': row[1],
            'latitud': row[2],
            'longitud': row[3],
            'descripcion': row[4],
            'servicios': row[5]
        })

    cursor.close()
    connection.close()

    return pueblos


def ponderar_pueblos_gpt(pueblos, origen, preferencias, valoraciones):
    prompt = f"Por favor, clasifica los siguientes pueblos en función de su cercanía al origen '{origen}', las preferencias del usuario {preferencias} y las valoraciones de otros usuarios {valoraciones}:\n\n"
    for i, pueblo in enumerate(pueblos):
        prompt += f"{i + 1}. {pueblo['nombre']} (Cercanía: {pueblo['distancia']} metros, Preferencias coincidentes: {pueblo['preferencias_coincidentes']}, Valoración: {pueblo['valoracion']} estrellas)\n"

    prompt += "\nOrdena los pueblos de mejor a peor opción, devolviendo los resultados en un array de JSON que contenga cada pueblo "
    prompt += "en el siguiente formato:\n"
    prompt += "{'nombre': 'Pueblo 1', 'latitud': 40.123, 'longitud': -3.456, 'distancia': 1234, 'preferencias_coincidentes': 2, 'valoracion': 4.5}\n"

    response = openai.Completion.create(engine="gpt-3.5-turbo", prompt=prompt, max_tokens=1500, n=1, stop=None, temperature=0) //Cambiar el engine

    choices = response.choices[0].text.strip().split(", ")
    ranked_pueblos = [pueblos[int(index) - 1] for index in choices]

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
        valoracion = get_valoracion_pueblo(pueblo['id'])  # Asumiendo que existe una función que obtiene la valoración de un pueblo

        if distancia <= distancia_desviacion:
            pueblos_cercanos.append({
                'nombre': pueblo['nombre'],
                'latitud': pueblo['latitud'],
                'longitud': pueblo['longitud'],
                'distancia': distancia,
                'preferencias_coincidentes': len(preferencias_coincidentes),
                'valoracion': valoracion
            })

    # Ordenar pueblos usando GPT de OpenAI
    pueblos_ponderados = ponderar_pueblos_gpt(pueblos_cercanos, origen, preferencias, valoraciones)

    # Seleccionar el número de paradas especificado por el usuario
    pueblos_seleccionados = pueblos_ponderados[:num_paradas]

    # Añadir pueblos a la ruta
    waypoints = [{'lat': pueblo['latitud'], 'lng': pueblo['longitud']} for pueblo in pueblos_seleccionados]
    ruta_final = gmaps.directions(origen, destino, waypoints=waypoints, optimize_waypoints=True)

    return jsonify({"ruta": ruta_final, "pueblos_sugeridos": pueblos_ponderados[:10]})

if __name__ == '__main__':
    app.run(debug=True)