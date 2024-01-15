from dataclasses import dataclass
from typing import Any, Dict, List, Optional, Tuple

SLS_LANGUAGE_ID = "sls"

StateName = str
StateDoc = str
ActualCompletion = Tuple[StateName, Optional[StateDoc]]
ActualCompletions = List[ActualCompletion]


@dataclass(frozen=True)
class StateParameters:
    parameters: Any
    documentation: Optional[str]


class StateNameCompletion:
    """
    This class provides the Salt Language Server with state name completion and
    documentation about the state.
    """

    def __init__(
        self,
        state_name: str,
        state_params: List[Any],
        module_docs: Dict[str, str],
    ) -> None:
        self.state_name = state_name
        self.state_params: Dict[str, StateParameters] = {}
        self.state_docs: Optional[str] = module_docs.get(state_name)

        for submod in state_params:
            submod_name = next(iter(submod.keys()))
            docs = module_docs.get(f"{state_name}.{submod_name}")

            self.state_params[submod_name] = StateParameters(submod[submod_name], docs)

        self.state_sub_names: List[str] = list(self.state_params.keys())

    def provide_subname_completion(
        self, prefix: Optional[str] = None
    ) -> Tuple[bool, ActualCompletions]:
        """
        This function provides the names and docstrings of the submodules of
        this state.
        If prefix is specified only return completion that starts with this prefix
        E.g. for the file state, it returns:
        [("absent", "doc of absent"), ("accumulated", "doc of accumulated"), ]

        The documentation is not guaranteed to be present and can be None.
        """
        completions = [
            (name, state_params.documentation)
            for name, state_params in self.state_params.items()
        ]
        if prefix is None:
            return True, completions
        return False, list(filter(lambda x: x[0].startswith(prefix), completions))

    def provide_param_completion(self, submod_name: str) -> List[str]:
        return list(self.state_params[submod_name].parameters.keys())


CompletionsDict = Dict[str, StateNameCompletion]
