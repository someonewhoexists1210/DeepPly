from openai import OpenAI
import os
from .classes import *
from .utils import zip_position_vector as zpv, diff_vector_to_semantic as dvts

KEY = os.getenv("OPENAI_API_KEY")
if not KEY:
    raise Exception("OPENAI_KEY not set in environment variables")

client = OpenAI(api_key=KEY)
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
    prompt = f""""""
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
                    "schema": ExplanationOutput.model_json_schema()
                }
            }
        )
        result = response.output_parsed

        if response.usage is None:
            raise Exception("No usage information returned from API")
        if result is None:
            raise Exception("No output returned from API")

        input_tokens = response.usage.input_tokens
        output_tokens = response.usage.output_tokens

        return result, input_tokens, output_tokens
    
    except Exception as e:
        raise e

    