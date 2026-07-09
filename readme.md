# V.I.C.T.O.R.
### Virtual Intelligence Checking Theories, Operations, and Results

An AI-powered mathematics learning platform that analyses handwritten mathematical working step-by-step without revealing the correct answer, while providing teachers with classroom analytics to identify student misconceptions and learning trends.

> 🌐 **Project Website:** *Coming Soon*  
> 🚀 **Live Demo:** https://victor-scrpn-drd.streamlit.app/  
> 🎥 **Project Demo:** *Coming Soon*

---

# Overview

As AI becomes increasingly common in education, students can receive complete worked solutions to mathematics problems within seconds. While this makes homework easier, it often removes the opportunity for students to identify and correct their own mistakes.

V.I.C.T.O.R. was designed to encourage productive struggle rather than dependency. Instead of solving an entire question, it analyses each mathematical step individually, identifies the first incorrect step, and provides feedback without revealing the correct solution. This allows students to revisit their own reasoning while giving teachers meaningful insights into both individual and class-wide learning.

---

# Key Features

## Student Features

- Upload handwritten mathematical working.
- OCR conversion into editable mathematical text.
- Ability to correct OCR recognition errors before analysis.
- Step-by-step mathematical validation.
- Highlights only the first incorrect step.
- AI-generated feedback without revealing the answer.
- Upload history and personal performance analytics.

---

## Teacher Features

- Create and manage classrooms.
- Create and manage mathematical topics.
- View individual student profiles.
- Track student performance across different topics.
- View class-wide analytics and heat maps.
- Identify students requiring additional support.
- Distinguish between conceptual and calculation-based errors.

---

# How It Works

1. The student logs into their assigned classroom.
2. The student selects the mathematical topic.
3. A photograph of the student's handwritten working is uploaded.
4. Gemini OCR converts the image into editable mathematical text.
5. The student can correct any OCR mistakes before analysis.
6. The Python mathematics engine validates every mathematical transformation using symbolic equivalence.
7. Once the first incorrect step is detected, the analysis stops.
8. Gemini generates feedback without revealing the correct solution.
9. The results are saved to the student's history and automatically synchronised with the teacher dashboard.

---

# What Makes V.I.C.T.O.R Different?

Most AI tools solve an entire mathematics problem once an error is detected.

V.I.C.T.O.R. deliberately avoids doing this.

Instead, it identifies only the student's first incorrect step and encourages them to continue solving the problem independently. The goal is to promote long-term understanding rather than answer copying while still giving teachers detailed insight into how their students think.

---

# Technology Stack

| Technology | Purpose |
|------------|---------|
| Python | Mathematical reasoning engine, backend logic and symbolic equivalence checking |
| Gemini API | OCR recognition and AI-generated educational feedback |
| Streamlit | Web application interface |
| Google Sheets API | User authentication, classroom management, history logs and analytics |
| Visual Studio Code | Development environment |
| Git & GitHub | Version control and project management |
| Codex & Claude | Development assistants for implementation guidance and debugging |

---

# Mathematical Topics Currently Supported

- Linear Algebra
- Factorisation
- Systems of Equations
- Area and Volume
- Inequalities

---

# Challenges

Throughout development, several technical challenges had to be addressed, including:

- Redesigning the authentication system when deploying the application to Streamlit.
- Integrating Google Sheets as a lightweight cloud database for user management and analytics.
- Reducing false positives while validating symbolic mathematical expressions.
- Allowing students to manually edit OCR output before mathematical analysis begins.

---

# What I Learned

This project allowed me to gain experience in:

- Designing and structuring a complete software application.
- Building mathematical logic using symbolic equivalence in Python.
- Deploying full-stack applications using Streamlit.
- Integrating external APIs into production workflows.
- Using GitHub for version control and iterative development.
- Designing software from both the student's and the teacher's perspective.

---

# Roadmap

Future development includes:

- Expanding the mathematical engine to support advanced topics such as probability, calculus and mathematical proofs.
- Adding longitudinal teacher analytics to monitor student progress over time.
- Allowing teachers to assign targeted practice directly through the platform.
- Using AI to identify recurring misconceptions and recommend personalised practice for individual students.

---

# License

This project is licensed under the MIT License.