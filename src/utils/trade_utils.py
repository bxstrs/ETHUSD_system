def get_execution_price(direction, market_state):
    return (
        market_state.ask if direction.name == "LONG"
        else market_state.bid
    )