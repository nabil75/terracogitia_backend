import database

async def postgres_select_query(query, *params):
    if database.pool is None:
        raise Exception("Pool is not initialized yet!")
    async with database.pool.acquire() as conn:
        return await conn.fetch(query, *params)
    
# SELECT COUNT
async def postgres_select_count_query(query):
    async with database.pool.acquire() as conn:
        row = await conn.fetchrow(query)
        return row[0]

# INSERT
async def postgres_insert_query(query, *params):
    async with database.pool.acquire() as conn:
        return await conn.fetchval(query, *params)

# UPDATE
async def postgres_update_query(query, *params):
    async with database.pool.acquire() as conn:
        await conn.execute(query, *params)
        return "Update query executed successfully."

# DELETE
async def postgres_delete_query(query, *params):
    async with database.pool.acquire() as conn:
        await conn.execute(query, *params)
        return "Delete query executed successfully."