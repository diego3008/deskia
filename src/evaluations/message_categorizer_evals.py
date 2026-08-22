from langsmith import Client
from dotenv import load_dotenv
load_dotenv()
client = Client()

dataset_name = "Message Categorizer Evals"
try:
    dataset = client.read_dataset(dataset_name=dataset_name)
    print(f"El dataset '{dataset_name}' ya existía. Usando el existente...")
except Exception:
    dataset = client.create_dataset(
        dataset_name=dataset_name,
        description="Casos de prueba para evaluar el nodo categorizador de intenciones."
    )
    print(f"Dataset '{dataset_name}' creado exitosamente.")



examples = [
    ({"message": "Hola buenas tardes"}, {"expected": "greeting"}),
    ({"message": "Buenos días, ¿qué tal?"}, {"expected": "greeting"}),
    ({"message": "Quiero agendar una cita para corte de cabello mañana a las 4 pm"}, {"expected": "new_appointment"}),
    ({"message": "¿Qué horarios tienen disponibles esta semana?"}, {"expected": "new_appointment"}),
    ({"message": "Hola, necesito programar una cita"}, {"expected": "new_appointment"}),
    ({"message": "¿Me puedes confirmar si hay espacio el viernes?"}, {"expected": "new_appointment"}),
    ({"message": "¿Cuánto cuesta la consulta general?"}, {"expected": "service_inquiry"}),
    ({"message": "¿Qué servicios ofrecen y cuáles son sus precios?"}, {"expected": "service_inquiry"}),
    ({"message": "¿Tienen disponibilidad para masajes?"}, {"expected": "service_inquiry"}),
    ({"message": "Necesito mover mi cita del viernes para el sábado a las 10am"}, {"expected": "reschedule_appointment"}),
    ({"message": "¿Puedo cambiar la hora de mi reserva?"}, {"expected": "reschedule_appointment"}),
    ({"message": "Quiero pasar mi cita al siguiente martes"}, {"expected": "reschedule_appointment"}),
    ({"message": "Cancélala por favor, ya no voy a poder asistir"}, {"expected": "cancel_appointment"}),
    ({"message": "Necesito cancelar mi cita agendada"}, {"expected": "cancel_appointment"}),
    ({"message": "Elimina mi reservación de la próxima semana"}, {"expected": "cancel_appointment"}),
    ({"message": "Sí, me parece perfecto ese horario"}, {"expected": "confirmation"}),
    ({"message": "Claro, de acuerdo"}, {"expected": "confirmation"}),
    ({"message": "Ok, go ahead"}, {"expected": "confirmation"}),
    ({"message": "No, mejor lo dejamos así gracias"}, {"expected": "decline"}),
    ({"message": "No thanks, not interested anymore"}, {"expected": "decline"}),
    ({"message": "Pésimo servicio, la persona nunca llegó y nadie me atendió"}, {"expected": "customer_complaint"}),
    ({"message": "Tengo un problema con el cobro que me hicieron"}, {"expected": "customer_complaint"}),
    ({"message": "Me encantó la atención, muchas gracias por la ayuda"}, {"expected": "customer_feedback"}),
    ({"message": "Excelente servicio, muy recomendado"}, {"expected": "customer_feedback"}),
    ({"message": "12345"}, {"expected": "unrelated"}),
    ({"message": "Me gusta la pizza con piña"}, {"expected": "unrelated"})
]

# 3. Subida masiva automática
# Agregar ejemplos de forma segura
for input_data, output_data in examples:
    client.create_example(
        inputs=input_data,
        outputs=output_data,
        dataset_id=dataset.id,
    )
print(f"¡Sincronización completada en el dataset '{dataset_name}'!")