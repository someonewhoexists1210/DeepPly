from openai import OpenAI
import os
from .classes import *
from .utils import zip_position_vector as zpv, diff_vector_to_semantic as dvts

KEY = os.getenv("OPENAI_API_KEY")
if not KEY:
    raise Exception("OPENAI_KEY not set in environment variables")

client = OpenAI(api_key=KEY)
schema = {
    "type": "object",
    "properties": {
        "explanations_per_position": {
            "type": "array",
            "items": {
            "type": "object",
            "properties": {
                "ply_number": {"type": "integer"},
                "explanation": {"type": "string"}
            },
            "required": ["ply_number", "explanation"],
            "additionalProperties": False
            }
        }, 
        "summary": {'type': 'string'}
    },
    "required": ["explanations_per_position", "summary"],
    "additionalProperties": False
}

def filter_analysis_for_explanation(analysis: GameAnalysisResult) -> ExplanationInput:
    filtered = {}
    filtered['player'] = analysis.player
    filtered['result'] = analysis.result
    filtered['time_control'] = analysis.time_control
    filtered['color'] = "white" if analysis.color else "black"

    filtered_analysis = []
    for i in range(not analysis.color, len(analysis.positions) - 1, 2):
        position_analysis = analysis.analysis[i // 2]
        position = analysis.positions[i]
        if not position_analysis.critical or not position_analysis.overall_mistake:
            continue

        pm = ""
        match (position_analysis.strategic_analysis.plan_match):
            case -1:
                pm = "No plan match"
            case 0:
                pm = "Partial plan match"
            case 1:
                pm = "Full plan match"
                
        strategic_obj = ConditionedPositionalPipelineResult(
            most_likely_followed_engine_plan=ConditionedCluster(RepresentationVector=zpv(position_analysis.strategic_analysis.user_plan.V), centipawn_evaluation=position_analysis.strategic_analysis.user_plan.E.cp, mate_evaluation=position_analysis.strategic_analysis.user_plan.E.mate),
            does_user_follow_most_likely_plan=pm,
            does_one_plan_dominate_other_engine_plans=position_analysis.strategic_analysis.domination,
            main_changes=zpv(dvts(position_analysis.strategic_analysis.V_gap)),
            user_mate_score=position_analysis.strategic_analysis.next_position_eval.mate,
            user_cp_score=position_analysis.strategic_analysis.next_position_eval.cp,
            engine_mate_score=position_analysis.strategic_analysis.E_ref.mate,
            engine_cp_score=position_analysis.strategic_analysis.E_ref.cp,
            is_acceptable_move=position_analysis.strategic_analysis.is_acceptable_move,
            is_strategic_mistake=position_analysis.strategic_analysis.strategic_mistake,
            short_positional_result_summary=position_analysis.strategic_analysis.result
        )
        position_obj = ConditionedPosition(
            fen=position.fen,
            ply_number=position.index,
            move=position.move,
            piece_moved=position.piece_moved,
            capture=position.capture,
            captured_piece=position.captured_piece,
            engine_move=position.engine_move,
            engine_piece_moved=position.engine_piece_moved,
            engine_capture=position.engine_capture,
            engine_captured_piece=position.engine_captured_piece,
            repetition=position.notes.get("repetition", False),
            fifty_move_rule=position.notes.get("fifty_move_rule", False)
        )

        conditioned_obj = ConditionedFullPositionResult(
            **strategic_obj.model_dump(),
            **position_obj.model_dump(),
            critical=position_analysis.critical,
            overall_mistake=position_analysis.overall_mistake,
            tactics_present=position_analysis.tactical_analysis,
            mistake_type=position_analysis.mistake_type
        )
        filtered_analysis.append(conditioned_obj)
        
    filtered['positions'] = filtered_analysis
    obj = ExplanationInput.model_validate(filtered)

    return obj

def generate_explanations(analysis: ExplanationInput) -> tuple[ExplanationOutput, int, int]:
    prompt = f"""
    You are a chess coach analysing a student's game. 
    You have access to the report of the moves of the game as well as certain data on both the positional and tactical aspects of each move compared to the engine's evaluation. 
    Go through the moves and provide reasonable explanations as to why the move played by the student is worse than the best engine move, based solely on the data provided. 
    You do not need to explain any more chess concepts than what is given in the data, no thinking, no inference. 
    Only provide explanations based on the data provided, but in your answer do not reference the data values. 
    The explanation crafted should not deviate from the data but should not seem exactly like the the summary of the move provided. 
    The explanation should be understandable to a chess student. 
    If the move is good, or if there is no data indicating that the move is bad, simply dont add anything for that move and go to the next one. 
    Be concise but informative in your explanations. 
    Use the following format for your response, strictly adhering to it and ensuring it is valid JSON according to the schema provided. 
    It is of upmost importance that you keep the explanation for each position to be no more than 150 words AT MAX. 
    The user will provide a JSON schema with all the data you need to reference to generate explanations.
    Also generate a concise summary of the game in at most 200 words, which should also be included in the output JSON.
    In your answers, mention the specific plans and moves by inferring the plan from the data provided, but do not reference the plan match value directly.
    Don't be too vague in your explanations by just saying that the user didnt follow the optimal plan, but also do not be too technical.
    Moves are in uci format, so the first 2 characters represent the square the piece moved from, and the next 2 characters represent the square the piece moved to.
    Make sure to mention the exact engine recommended move in each moves explanation and why it is better than the move played by the student in your explanations.
    Also do not be overly negative in your explanations, even if the move played was a mistake, try to find some positive aspect in the move played by the student and mention it in the explanation as well, while still clearly explaining why the engine move is better.
    And dont continuously say that the user didnt follow the engine's plan, but also mention exactly what plan.
    """
    try:
        response = client.responses.parse(
            model="gpt-4.1-nano-2025-04-14",
            input=[
                {
                    'role': "developer",
                    'content': prompt
                },
                {
                    "role": "user",
                    "content": analysis.model_dump_json()
                }
            ],
            temperature=0.2,
            max_output_tokens=2000,
            text={
                "format": {
                    "type": "json_schema",
                    "name": "ExplanationOutput",
                    "strict": True,
                    "schema": schema
                }
            }
        )
        result = response.output_text
        result = ExplanationOutput.model_validate_json(result)

        if response.usage is None:
            raise Exception("No usage information returned from API")
        if result is None:
            raise Exception("No output returned from API")

        input_tokens = response.usage.input_tokens
        output_tokens = response.usage.output_tokens

        return result, input_tokens, output_tokens
    
    except Exception as e:
        raise e

    