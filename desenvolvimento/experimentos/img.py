import asyncio, base64, json, sys, time
sys.path.insert(0, "/home/pedro/cordel-generator")
import ai
from ai.providers.openai import tools as ot
from app import prompts, workflow  # workflow carrega o .env
fato = json.load(open(sys.argv[2]))["fato"]
prompt = prompts.prompt_xilogravura(fato["fato"], fato["imagens_concretas"])
async def um(nome, modelo, qualidade):
    tool = ot.image_generation(model=modelo, size="1536x1024", quality=qualidade, output_format="png")
    params = ai.InferenceRequestParams(tool_calling=ai.ToolCallingParams(tool_choice=ai.ToolChoiceMode.REQUIRED))
    t0 = time.monotonic()
    async with ai.stream(ai.get_model("openai:gpt-5.4-mini"), [ai.user_message(prompt)], tools=[tool], params=params) as s:
        async for _ in s: pass
    f = s.message.files[0]; d = f.data if isinstance(f.data, bytes) else base64.b64decode(f.data.split(",")[-1])
    open(f"{sys.argv[1]}/{nome}.png", "wb").write(d)
    return nome, round(time.monotonic() - t0), s.usage.raw if s.usage else None, s.message.files[0].media_type
async def main():
    for r in await asyncio.gather(um("img2-low", "gpt-image-2", "low"), um("img2-medium", "gpt-image-2", "medium"), um("img1mini-medium", "gpt-image-1-mini", "medium")):
        print(r)
asyncio.run(main())
