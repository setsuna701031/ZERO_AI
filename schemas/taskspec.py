class TaskSpec:

    def __init__(self, goal, tool=None, params=None):

        self.goal = goal
        self.tool = tool
        self.params = params or {}

    def to_dict(self):

        return {
            "goal": self.goal,
            "tool": self.tool,
            "params": self.params
        }