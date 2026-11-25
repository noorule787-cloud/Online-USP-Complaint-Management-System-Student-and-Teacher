import speech_recognition as sr

recognizer = sr.Recognizer()

with sr.Microphone() as source:
    print("Please wait... Adjusting microphone...")
    recognizer.adjust_for_ambient_noise(source, duration=2)

    print("Now speak your complaint clearly...")
    audio = recognizer.listen(source, timeout=10, phrase_time_limit=15)

try:
    text = recognizer.recognize_google(audio)
    print("\nComplaint Text:")
    print(text)

except sr.UnknownValueError:
    print("Sorry, I could not understand your voice.")

except sr.RequestError:
    print("Could not connect to Google Speech Recognition.")