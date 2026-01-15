import inspect
import sherpa_onnx

print("=== OfflineRecognizer.from_sense_voice ===")
print(inspect.signature(sherpa_onnx.OfflineRecognizer.from_sense_voice))

print("\n=== OfflineRecognizer.create_stream ===")
# create_stream might not have arguments for sense voice, but let's check
# Usually in C++ API it's just create_stream()
# But maybe there are args?
print(inspect.signature(sherpa_onnx.OfflineRecognizer.create_stream))

# Check if there is a 'language' param in create_stream or decode_stream?
# decode_stream takes a stream.
