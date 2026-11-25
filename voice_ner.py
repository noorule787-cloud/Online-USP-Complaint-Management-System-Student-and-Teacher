
import speech_recognition as sr


def record_voice():

    recognizer = sr.Recognizer()

    try:

        with sr.Microphone() as source:

            print("======================================")
            print(" VOICE COMPLAINT")
            print("======================================")

            print("Please wait... Adjusting microphone...")

            recognizer.adjust_for_ambient_noise(
                source,
                duration=2
            )

            # Better settings for normal speech
            recognizer.energy_threshold = 250
            recognizer.dynamic_energy_threshold = True
            recognizer.pause_threshold = 2
            recognizer.phrase_threshold = 0.3
            recognizer.non_speaking_duration = 0.5

            print("")
            print(" RECORDING STARTED")
            print("Please speak clearly...")
            print("")

            audio = recognizer.listen(
                source,
                timeout=30,
                phrase_time_limit=60
            )

            print("")
            print(" Recording completed")
            print(" Converting voice to text...")
            print("")

        # Convert voice to text
        text = recognizer.recognize_google(
            audio,
            language="en-US"
        )

        text = text.strip()

        if not text:

            print("ERROR: Empty voice text.")
            return None

        print("======================================")
        print(" RECOGNIZED TEXT")
        print("======================================")
        print(text)
        print("======================================")

        return text


    except sr.WaitTimeoutError:

        print("ERROR: No voice detected.")
        return None


    except sr.UnknownValueError:

        print("ERROR: Sorry, I could not understand your voice.")
        return None


    except sr.RequestError as e:

        print("ERROR: Speech recognition service unavailable.")
        print(e)
        return None


    except OSError as e:

        print("ERROR: Microphone problem.")
        print(e)
        return None


    except Exception as e:

        print("ERROR:", str(e))
        return None


if __name__ == "__main__":

    result = record_voice()

    if result:

        print("VOICE_TEXT_START")
        print(result)
        print("VOICE_TEXT_END")

