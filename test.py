from ursina import *

app = Ursina()
cube = Entity(model='cube', color=color.azure, scale=(1,1,1))

camera.orthographic = True   # для 2D сверху
camera.fov = 20
camera.position = (10, 10, -30)

Text(text='Привет', position=(-.5,.4))

Button(text='Кнопка', scale=.1, color=color.azure)#, on_click=my_function)

WindowPanel(title="Меню", content=(Button('hi'), Button('not hi')))

cube.animate_x(5, duration=1)   # плавный сдвиг
cube.animate_color(color.red, duration=2)



def update():
    cube.x += held_keys['d'] * 0.1
    cube.x -= held_keys['a'] * 0.1
    cube.y += held_keys['w'] * 0.1
    cube.y -= held_keys['s'] * 0.1

from ursina import invoke

def hello():
    print("Привет через 2 сек")

invoke(hello, delay=2)



app.run()