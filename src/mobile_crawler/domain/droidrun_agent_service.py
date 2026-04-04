"""DroidRun agent service integration for mobile crawler."""

import asyncio
import json
import logging
import time
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import List, Optional, Dict, Any

from mobile_crawler.config.config_manager import ConfigManager
from mobile_crawler.domain.models import ActionResult, AIResponse, AIAction, BoundingBox
from mobile_crawler.infrastructure.ai_interaction_repository import AIInteraction, AIInteractionRepository

logger = logging.getLogger(__name__)


@dataclass
class DroidRunGoal:
    """Goal representation for DroidRun agent."""
    description: str
    max_steps: int = 15
    reasoning: bool = True
    app_package: Optional[str] = None


@dataclass
class DroidRunResult:
    """Result from DroidRun agent execution."""
    success: bool
    steps_completed: int
    actions_taken: List[Dict[str, Any]]
    final_state: Dict[str, Any]
    error_message: Optional[str] = None
    total_duration_ms: float = 0.0


class DroidRunAgentService:
    """Service for integrating DroidRun AI agents with the mobile crawler."""

    def __init__(
        self,
        config_manager: ConfigManager,
        ai_interaction_repository: AIInteractionRepository,
        device_id: str
    ):
        """Initialize DroidRun agent service.

        Args:
            config_manager: Configuration manager for crawler settings
            ai_interaction_repository: Repository for logging AI interactions
            device_id: ADB device identifier
        """
        self.config_manager = config_manager
        self.ai_interaction_repository = ai_interaction_repository
        self.device_id = device_id
        self._droid_agent = None
        self._is_initialized = False

    def _get_droidrun_config(self) -> Dict[str, Any]:
        """Convert crawler configuration to DroidRun format.

        Returns:
            DroidRun configuration dictionary
        """
        # Get LLM configuration from crawler config
        ai_provider = self.config_manager.get('ai_provider', 'gemini')
        ai_model = self.config_manager.get('ai_model', 'gemini-1.5-flash')

        # Map crawler providers to DroidRun format
        provider_mapping = {
            'gemini': 'GoogleGenAI',
            'openai': 'OpenAI',
            'anthropic': 'AnthropicAI',
            'ollama': 'Ollama'
        }

        droid_provider = provider_mapping.get(ai_provider, 'GoogleGenAI')

        config = {
            'agent': {
                'max_steps': self.config_manager.get('max_crawl_steps', 15),
                'reasoning': self.config_manager.get('droidrun_reasoning_mode', True),
                'streaming': False,
                'max_retries': self.config_manager.get('ai_retry_count', 2)
            },
            'device': {
                'platform': 'android',
                'device_id': self.device_id,
                'auto_setup': False  # We handle device setup separately
            },
            'llm_profiles': {
                'manager': {
                    'provider': droid_provider,
                    'model': ai_model,
                    'temperature': 0.1
                },
                'executor': {
                    'provider': droid_provider,
                    'model': ai_model,
                    'temperature': 0.0
                },
                'fast_agent': {
                    'provider': droid_provider,
                    'model': ai_model,
                    'temperature': 0.0
                }
            },
            'tools': {
                # Disable certain tools that conflict with our infrastructure
                'disabled': ['portal_screenshot']  # We use our own screenshot capture
            },
            'telemetry': {
                'enabled': False  # Disable to avoid conflicts with our monitoring
            }
        }

        # Add API keys based on provider
        if ai_provider == 'gemini':
            api_key = self.config_manager.get('gemini_api_key')
            if api_key:
                config['llm_profiles']['manager']['api_key'] = api_key
                config['llm_profiles']['executor']['api_key'] = api_key
                config['llm_profiles']['fast_agent']['api_key'] = api_key
        elif ai_provider == 'openai':
            api_key = self.config_manager.get('openai_api_key')
            if api_key:
                config['llm_profiles']['manager']['api_key'] = api_key
                config['llm_profiles']['executor']['api_key'] = api_key
                config['llm_profiles']['fast_agent']['api_key'] = api_key
        elif ai_provider == 'anthropic':
            api_key = self.config_manager.get('anthropic_api_key')
            if api_key:
                config['llm_profiles']['manager']['api_key'] = api_key
                config['llm_profiles']['executor']['api_key'] = api_key
                config['llm_profiles']['fast_agent']['api_key'] = api_key

        return config

    async def _initialize_agent(self) -> None:
        """Initialize DroidRun agent with current configuration."""
        if self._is_initialized:
            return

        try:
            # Import DroidRun components
            from droidrun.agent.droid.droid_agent import DroidAgent
            from droidrun.config.droidrun_config import DroidRunConfig

            # Create DroidRun configuration
            config_dict = self._get_droidrun_config()
            config = DroidRunConfig.from_dict(config_dict)

            # Initialize DroidRun agent
            self._droid_agent = DroidAgent(config=config)

            # Perform any necessary setup
            await self._droid_agent.setup()

            self._is_initialized = True
            logger.info("DroidRun agent initialized successfully")

        except Exception as e:
            logger.error(f"Failed to initialize DroidRun agent: {e}")
            raise

    def _create_exploration_goal(
        self,
        app_package: str,
        max_steps: int,
        exploration_objective: Optional[str] = None
    ) -> DroidRunGoal:
        """Create a goal for app exploration.

        Args:
            app_package: Target app package name
            max_steps: Maximum steps to execute
            exploration_objective: Optional specific exploration objective

        Returns:
            DroidRunGoal for app exploration
        """
        if exploration_objective:
            description = f"Explore the {app_package} app with focus on: {exploration_objective}"
        else:
            description = (
                f"Explore the {app_package} app systematically. "
                f"Navigate through different screens, interact with UI elements, "
                f"and discover the app's functionality. Focus on user flows like "
                f"registration, login, main features, and settings."
            )

        return DroidRunGoal(
            description=description,
            max_steps=max_steps,
            reasoning=self.config_manager.get('droidrun_reasoning_mode', True),
            app_package=app_package
        )

    async def execute_exploration_task(
        self,
        run_id: int,
        app_package: str,
        max_steps: int = 15,
        exploration_objective: Optional[str] = None
    ) -> DroidRunResult:
        """Execute an app exploration task using DroidRun agent.

        Args:
            run_id: Crawler run ID for logging
            app_package: Target app package name
            max_steps: Maximum steps to execute
            exploration_objective: Optional specific exploration objective

        Returns:
            DroidRunResult with execution details
        """
        start_time = time.time()

        try:
            # Initialize agent if needed
            await self._initialize_agent()

            # Create exploration goal
            goal = self._create_exploration_goal(app_package, max_steps, exploration_objective)

            # Log agent request
            self._log_agent_interaction(run_id, goal, None, None)

            # Execute the goal using DroidRun agent
            logger.info(f"Executing DroidRun agent goal: {goal.description[:100]}...")

            result = await self._droid_agent.run(
                goal=goal.description,
                max_steps=goal.max_steps
            )

            duration_ms = (time.time() - start_time) * 1000

            # Convert DroidRun result to our format
            droid_result = DroidRunResult(
                success=result.get('success', False),
                steps_completed=result.get('steps_completed', 0),
                actions_taken=result.get('actions_taken', []),
                final_state=result.get('final_state', {}),
                error_message=result.get('error_message'),
                total_duration_ms=duration_ms
            )

            # Log successful interaction
            self._log_agent_interaction(run_id, goal, result, None)

            logger.info(f"DroidRun agent completed: {droid_result.steps_completed} steps in {duration_ms:.1f}ms")
            return droid_result

        except Exception as e:
            duration_ms = (time.time() - start_time) * 1000
            error_msg = str(e)

            # Log failed interaction
            self._log_agent_interaction(run_id, goal, None, error_msg)

            logger.error(f"DroidRun agent execution failed: {error_msg}")
            return DroidRunResult(
                success=False,
                steps_completed=0,
                actions_taken=[],
                final_state={},
                error_message=error_msg,
                total_duration_ms=duration_ms
            )

    def _log_agent_interaction(
        self,
        run_id: int,
        goal: DroidRunGoal,
        result: Optional[Dict[str, Any]],
        error_message: Optional[str]
    ) -> None:
        """Log agent interaction to the database.

        Args:
            run_id: Crawler run ID
            goal: The goal that was executed
            result: Agent execution result (if successful)
            error_message: Error message (if failed)
        """
        try:
            # Create request data
            request_data = {
                "goal_description": goal.description,
                "max_steps": goal.max_steps,
                "reasoning_mode": goal.reasoning,
                "app_package": goal.app_package
            }

            # Create response data
            response_data = None
            if result:
                response_data = {
                    "success": result.get('success', False),
                    "steps_completed": result.get('steps_completed', 0),
                    "actions_taken": result.get('actions_taken', []),
                    "final_state": result.get('final_state', {})
                }

            # Create AI interaction record
            interaction = AIInteraction(
                id=None,
                run_id=run_id,
                step_number=1,  # DroidRun handles multiple steps internally
                timestamp=datetime.now(),
                request_json=json.dumps(request_data),
                screenshot_path=None,  # DroidRun handles screenshots internally
                response_raw=json.dumps(response_data) if response_data else None,
                response_parsed_json=json.dumps(response_data) if response_data else None,
                tokens_input=None,  # Token counting handled by DroidRun
                tokens_output=None,
                latency_ms=None,  # Will be calculated by calling code
                success=error_message is None,
                error_message=error_message,
                retry_count=0
            )

            self.ai_interaction_repository.create_ai_interaction(interaction)

        except Exception as e:
            logger.warning(f"Failed to log agent interaction: {e}")

    def convert_droidrun_actions_to_crawler_format(
        self,
        droidrun_actions: List[Dict[str, Any]]
    ) -> List[AIAction]:
        """Convert DroidRun actions to crawler AIAction format.

        Args:
            droidrun_actions: List of actions from DroidRun

        Returns:
            List of AIAction objects
        """
        converted_actions = []

        for action_data in droidrun_actions:
            try:
                # Extract action details
                action_type = action_data.get('action', 'unknown')
                description = action_data.get('description', '')
                coordinates = action_data.get('coordinates')
                text = action_data.get('text')

                # Create bounding box if coordinates available
                bounding_box = None
                if coordinates and len(coordinates) >= 2:
                    x, y = coordinates[:2]
                    # Create a small bounding box around the point
                    bounding_box = BoundingBox(
                        top_left=(max(0, x-10), max(0, y-10)),
                        bottom_right=(x+10, y+10)
                    )

                # Map DroidRun action types to crawler action types
                action_mapping = {
                    'click': 'click',
                    'tap': 'click',
                    'type': 'input',
                    'swipe': 'scroll_down',  # Simplified mapping
                    'scroll': 'scroll_down',
                    'back': 'back'
                }

                mapped_action = action_mapping.get(action_type, 'click')

                # Create AIAction
                ai_action = AIAction(
                    action=mapped_action,
                    action_desc=description or f"DroidRun {action_type}",
                    target_bounding_box=bounding_box,
                    input_text=text,
                    reasoning=action_data.get('reasoning', '')
                )

                converted_actions.append(ai_action)

            except Exception as e:
                logger.warning(f"Failed to convert DroidRun action {action_data}: {e}")
                continue

        return converted_actions

    async def cleanup(self) -> None:
        """Cleanup DroidRun agent resources."""
        if self._droid_agent:
            try:
                await self._droid_agent.cleanup()
                logger.info("DroidRun agent cleaned up successfully")
            except Exception as e:
                logger.warning(f"Error during DroidRun agent cleanup: {e}")
            finally:
                self._droid_agent = None
                self._is_initialized = False