import sys
import os

def main():
    if len(sys.argv) < 6:
        print("Usage: python run_rvc.py <input_audio> <model_path> <pitch> <output_path> <device>")
        sys.exit(1)
        
    input_audio = sys.argv[1]
    model_path = sys.argv[2]
    pitch = int(sys.argv[3])
    output_path = sys.argv[4]
    device = sys.argv[5]
    
    # We load rvc_python here inside the portable python environment
    from rvc_python.infer import RVCInference
    
    print(f"Loading model: {model_path} on {device}")
    # Initialize RVC Inference
    rvc = RVCInference(device=device)
    
    try:
        rvc.load_model(model_path)
    except Exception as e:
        print("Failed to load on CUDA, trying CPU...")
        rvc = RVCInference(device="cpu")
        rvc.load_model(model_path)
        
    print(f"Running inference on {input_audio}")
    rvc.infer_file(input_audio, output_path, f0_up_key=pitch)
    print("Done!")

if __name__ == "__main__":
    main()
