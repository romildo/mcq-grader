# grade_exams.py
import pandas as pd
import argparse
import sys
import omr_utils

def compare_answers(student_answer_str, key_answer_str):
    """Compares the student's answer with the answer key, applying special rules."""
    # Coalesce NaN or empty strings to a 'BLANK' representation for comparison
    if pd.isna(student_answer_str) or str(student_answer_str).strip() in ["", "BLANK"]:
        student_set = set()
    else:
        student_set = set(str(student_answer_str).split(','))

    if pd.isna(key_answer_str) or str(key_answer_str).strip() == "":
        return False

    key_answer_str = str(key_answer_str)
    
    # Mode 1: Inclusive OR (e.g., A+B+E)
    if '+' in key_answer_str:
        key_set = set(key_answer_str.split('+'))
        return bool(student_set) and student_set.issubset(key_set)
        
    # Mode 2: Exclusive AND (e.g., ABE or just A)
    else:
        key_set = set(list(key_answer_str))
        return student_set == key_set

def main(args):
    print("Starting the grading process with inline answer key formatting...")
    
    try:
        df_answers = pd.read_csv(args.answers_csv)
        df_keys = pd.read_csv(args.keys_csv)
    except FileNotFoundError as e:
        print(f"Error: File not found! Please check if '{e.filename}' is correct.", file=sys.stderr)
        sys.exit(1)
        
    # Clean up confidence columns immediately
    confidence_cols = [col for col in df_answers.columns if 'Confidence_Q' in col]
    df_formatted_results = df_answers.drop(columns=confidence_cols)
        
    if 'Exam_Type' not in df_keys.columns:
        print("Error: answer key CSV is missing required column 'Exam_Type'.", file=sys.stderr)
        sys.exit(1)

    if 'Exam_Type' not in df_formatted_results.columns:
        print("Error: answers CSV is missing required column 'Exam_Type'.", file=sys.stderr)
        sys.exit(1)

    df_keys['Exam_Type'] = df_keys['Exam_Type'].map(omr_utils.normalize_exam_type)
    df_formatted_results['Exam_Type'] = df_formatted_results['Exam_Type'].map(omr_utils.normalize_exam_type)

    duplicate_key_types = sorted(
        exam_type for exam_type in df_keys['Exam_Type'].dropna().unique()
        if exam_type and (df_keys['Exam_Type'] == exam_type).sum() > 1
    )
    if duplicate_key_types:
        print(
            "Error: answer key CSV has duplicate Exam_Type values after normalization: "
            + ", ".join(duplicate_key_types),
            file=sys.stderr,
        )
        sys.exit(1)

    df_keys.set_index('Exam_Type', inplace=True)
    
    scores = []
    normalized_scores = []
    question_cols = [col for col in df_keys.columns if col.startswith('Q')]
    num_questions = len(question_cols)

    for index, student_row in df_formatted_results.iterrows():
        correct_answers = 0
        exam_type = student_row.get('Exam_Type')
        
        if not exam_type or pd.isna(exam_type) or exam_type not in df_keys.index:
            print(f"Warning: Answer key not found for Exam Type '{exam_type}' ... Assigning score 0.")
            scores.append(0)
            normalized_scores.append(0.0)
            continue
            
        correct_key_row = df_keys.loc[exam_type]
        
        for col in question_cols:
            student_answer = student_row.get(col)
            correct_answer = correct_key_row.get(col)
            
            is_correct = compare_answers(student_answer, correct_answer)
            
            if is_correct:
                correct_answers += 1
            else:
                # --- NEW: Format the cell for incorrect answers ---
                student_answer_display = student_answer if pd.notna(student_answer) else "BLANK"
                formatted_answer = f"{student_answer_display}~{correct_answer}"
                df_formatted_results.loc[index, col] = formatted_answer
                
        scores.append(correct_answers)
        normalized_score = round((correct_answers / num_questions) * 10, 2) if num_questions > 0 else 0.0
        normalized_scores.append(normalized_score)
        
        print(f"  -> Student ID {student_row.get('Student_ID', 'N/A')}: {correct_answers} of {num_questions} correct.")

    df_formatted_results['Final_Score'] = scores
    df_formatted_results['Score_0_to_10'] = normalized_scores
    
    df_formatted_results.to_csv(args.output_csv, index=False)
    
    print(f"\nGrading complete! Results saved to '{args.output_csv}'.")

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Grades exams from a CSV of student answers and an answer key CSV.")
    parser.add_argument("--answers-csv", required=True, help="Path to the CSV file with extracted student answers.")
    parser.add_argument("--keys-csv", required=True, help="Path to the CSV file with the exam answer keys.")
    parser.add_argument("--output-csv", required=True, help="Path for the output CSV file with final scores.")
    
    main(parser.parse_args())