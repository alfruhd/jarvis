import sounddevice as sd
import numpy as np
from resemblyzer import VoiceEncoder, preprocess_wav
import time

encoder = VoiceEncoder()

duration = 5  # seconds
sample_rate = 16000

print("==================================================")
print("🎙️ VOICE ENROLLMENT: Get ready to speak.")
print("When it starts, say clearly: 'Jarvis, hey Jarvis, Zoe, hey Zoe'")
print("==================================================")

for i in range(3, 0, -1):
    print(f"Starting in {i}...")
    time.sleep(1)

print("\n🔴 RECORDING NOW... (Speak into your M1 Mac microphone)")
audio = sd.rec(int(duration * sample_rate), samplerate=sample_rate, channels=1, dtype='float32')
sd.wait()
print("✅ Recording complete!")

# Flatten and preprocess audio for Resemblyzer
audio_flat = audio.squeeze()
# Save temporarily or process directly
np.save("temp_voice.npy", audio_flat)

# Generate embedding vector
wav = preprocess_wav(audio_flat, source_sr=sample_rate)
embed = encoder.embed_utterance(wav)

# Save your official voiceprint
np.save("alfred_voice.npy", embed)
print("🚀 Success! Your secure voice profile has been saved as 'alfred_voice.npy'.")
