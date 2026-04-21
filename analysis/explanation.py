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
                "move": {"type": "string"},
                "explanation": {"type": "string"}
            },
            "required": ["move", "explanation"],
            "additionalProperties": False
            }
        }
    },
    "required": ["explanations_per_position"],
    "additionalProperties": False
}

def filter_analysis_for_explanation(analysis: GameAnalysisResult) -> ExplanationInput:
    filtered = {}
    filtered['player'] = analysis.player
    filtered['color'] = "white" if analysis.color else "black"

    filtered_analysis = []
    for i in range(not analysis.color, len(analysis.positions) - 1, 2):
        position_analysis = analysis.analysis[i // 2]
        position = analysis.positions[i]
        if not position_analysis.critical and not position_analysis.overall_mistake:
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
            move_number=position.index // 2 + 1,
            move=position.move,
            piece_moved=position.piece_moved,
            repetition=position.notes.get("repetition", False),
            fifty_move_rule=position.notes.get("fifty_move_rule", False)
        )

        conditioned_obj = ConditionedFullPositionResult(
            **strategic_obj.model_dump(),
            **position_obj.model_dump(),
            critical=position_analysis.critical,
            overall_mistake=position_analysis.overall_mistake,
            mistake_type=position_analysis.mistake_type
        )
        filtered_analysis.append(conditioned_obj)
        
    filtered['positions'] = filtered_analysis
    obj = ExplanationInput.model_validate(filtered)

    return obj

def generate_explanations(analysis: ExplanationInput) -> tuple[ExplanationOutput, int, int]:
    prompt = f"""
    You are a chess coach analysing a student's game. You have access to the report of the moves of the game as well as certain data on both the positional and tactical aspects of each move compared to the engine's evaluation. Go through the moves and provide reasonable explanations as to why the move played by the student is worse than the best engine move, based solely on the data provided. You do not need to explain any more chess concepts than what is given in the data, no thinking, no inference. Only provide explanations based on the data provided, but in your answer do not reference the data values. The explanation crafted should not deviate from the data but should not seem exactly like the the summary of the move provided. The explanation should be understandable to a chess student.  If the move is good, or if there is no data indicating that the move is bad, simply say "Good move, no mistakes detected". Be concise but informative in your explanations. Use the following format for your response, strictly adhering to it and ensuring it is valid JSON according to the schema provided. It is of upmost importance that you keep the explanation for each position to be no more than 200 words AT MAX. The user will provide a JSON schema with all the data you need to reference to generate explanations.
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
        print(response)
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

    