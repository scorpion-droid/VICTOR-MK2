from __future__ import annotations

import tkinter as tk
from tkinter import filedialog, messagebox, scrolledtext
from App.checker import detect_first_error
from App.sanitiser import clean_noisy_ocr
from App.ocr import extract_steps_from_image

class MathOCRApp: 
    def __init__(self, root: tk.Tk): 
        self.root = root
        self.root.title("Math Error Checker")
        self.root.geometry("900x650")
        self.root.configure(bg="#f4f1ea")

        self.image_path: str | None = None

        title = tk.Label(
            root, 
            text="V.I.C.T.O.R",
            font=("Old Standard TT", 24, "bold"),
            bg="#f4f1ea",
            fg="#1f2937",
        )
        title.pack(pady=(20,6))

        subtitle = tk.Label (
            root, 
            text="Upload a photo of your math steps for mistakes",
            font = ("Old Standard TT", 11),
            bg="#f4f1ea",
            fg="#4b5563",
        )
        subtitle.pack(pady=(0, 16))

        button_frame = tk.Frame(root, bg="#f4f1ea")
        button_frame.pack(pady=10)

        upload_button = tk.Button(
            button_frame,
            text="Choose Image",
            command = self.choose_image, 
            font=("Old Standard TT",11,"bold"),
            bg="#2563eb",
            fg="white",
            padx=16,
            pady=10,
            relief="flat",
        )
        upload_button.grid(row=0, column=0, padx=8)

        ocr_button = tk.Button(
            button_frame,
            text="Check",
            command=self.run_ocr_and_check,
            font=("Old Standard TT", 11, "bold"),
            bg="#059669",
            fg="white",
            padx=16,
            pady=10,
            relief="flat",
        )
        ocr_button.grid(row=0, column=1, padx=8)

        clear_button = tk.Button(
            button_frame,
            text="Clear",
            command=self.clear_all,
            font=("Helvetica", 11, "bold"),
            bg="#ef4444",
            fg="white",
            padx=16,
            pady=10,
            relief="flat",
        )
        clear_button.grid(row=0, column=2, padx=8)

        self.file_label = tk.Label(
            root, 
            text="No Image Selected Yet.", 
            font = ("Old Standard TT", 14), 
            bg="#f4f1ea",
            fg="#6b7280",
        )
        self.file_label.pack(pady=(8, 12))

        content = tk.Frame(root, bg="#f4f1ea")
        content.pack(fill="both", expand=True, padx=20, pady=10)

        left = tk.LabelFrame(content, text="OCR Output", bg="#ffffff", fg="#111827", padx=10, pady=10)
        left.pack(side="left", fill="both", expand=True, padx=(0, 10))

        right = tk.LabelFrame(content, text="Checker Result", bg="#ffffff", fg="#111827", padx=10, pady=10)
        right.pack(side="right", fill="both", expand=True, padx=(10, 0))

        self.ocr_text = scrolledtext.ScrolledText(left, wrap="word", font=("Courier New", 11), height=18)
        self.ocr_text.pack(fill="both", expand=True)

        self.result_text = scrolledtext.ScrolledText(right, wrap="word", font=("Courier New", 11), height=18)
        self.result_text.pack(fill="both", expand=True)

        self.status = tk.Label(
            root,
            text="Ready.",
            font=("Old Standard TT", 13),
            bg="#f4f1ea",
            fg="#374151",
        )
        self.status.pack(pady=(6, 14))

    def choose_image(self) -> None: 
        filetypes = [
            ("Image Files", "*.png *.jpg *.bmp *.jpeg *.tif *.tiff *.hiec"),
            ("All files", "*.*"),
        ]
        path = filedialog.askopenfilename(title="Select a math image", filetypes=filetypes)
        if not path: 
            return
        
        self.image_path = path
        self.file_label.config(text=f"Selected: {path}")
        self.status.config(text="Image selected.")

    def run_ocr_and_check(self) -> None: 
        if not self.image_path:
            messagebox.showwarning("No image", "Please choose an image first.")
            return
        
        # 1. Determine the source of the steps: User-edited text or fresh OCR?
        manual_text = self.ocr_text.get("1.0", tk.END).strip()
        
        if manual_text and manual_text != "(No readable text found.)":
            # If the user has typed/edited in the box, use that instead of re-running OCR
            steps = [line.strip() for line in manual_text.splitlines() if line.strip()]
            self.status.config(text="Using manual edits...")
        else:
            # Otherwise, perform the fresh OCR extraction
            self.ocr_text.delete("1.0", tk.END)
            self.result_text.delete("1.0", tk.END)
            try: 
                self.status.config(text="Extracting handwriting layout...")
                self.root.update_idletasks()
                steps = extract_steps_from_image(self.image_path)
            except Exception as exc:
                messagebox.showerror("OCR error", str(exc))
                self.status.config(text="OCR Failed.")
                return
            
            if not steps: 
                self.ocr_text.insert(tk.END, "(No readable text found.)")
                self.result_text.insert(tk.END, "Nothing to check.")
                self.status.config(text="Image scanned, but no text found.")
                return

            # Update the UI with initial OCR findings
            self.ocr_text.insert(tk.END, "\n".join(steps))
        
        # 2. Refine the steps with AI
        self.status.config(text="Refining math text with AI...")
        self.root.update_idletasks()
        
        try:
            sanitized_text = clean_noisy_ocr(steps)
            steps = [line.strip() for line in sanitized_text.splitlines() if line.strip()]
            
            self.ocr_text.delete("1.0", tk.END)
            self.ocr_text.insert(tk.END, "\n".join(steps))
        except Exception as exc:
            error_msg = str(exc)
            if "429" in error_msg or "RESOURCE_EXHAUSTED" in error_msg:
                messagebox.showwarning("Rate Limit", "AI is busy. Please wait a moment and try again.")
            else:
                messagebox.showerror("Sanitizer error", f"AI cleaning failed: {exc}")
            self.status.config(text="Sanitization Failed.")
            return

        # 3. Verify math steps
        self.status.config(text="Verifying mathematical steps...")
        result = detect_first_error(steps)
        
        self.result_text.delete("1.0", tk.END)
        self.result_text.insert(tk.END, f"Passed: {result.passed}\n")
        self.result_text.insert(tk.END, f"Message: {result.message}\n")
        
        if result.first_error_index is not None:
            self.result_text.insert(tk.END, f"First error in steps: {result.first_error_index + 1}\n")

        self.status.config(text="Checking Complete.")

    def clear_all(self) -> None:
        self.image_path = None
        self.file_label.config(text="No image selected yet.")
        self.ocr_text.delete("1.0", tk.END)
        self.result_text.delete("1.0", tk.END)
        self.status.config(text="Cleared.")

def main() -> None:
    root = tk.Tk()
    app = MathOCRApp(root)
    root.mainloop()


if __name__ == "__main__":
    main()