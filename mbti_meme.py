import os
from tkinter import *
import tkinter.font
from PIL import ImageTk, Image
import tkinter.ttk as ttk
from tkinter import filedialog
from tkinter import messagebox
import copy
import imghdr
import math
import warnings
from win32api import GetSystemMetrics
import datetime
import shutil

#<zoom tkinter class>
class MainWindow(ttk.Frame):#https://stackoverflow.com/questions/41656176/tkinter-canvas-zoom-move-pan
    """ Main window class """
    def __init__(self, mainframe, path):
        """ Initialize the main Frame """
        ttk.Frame.__init__(self, master=mainframe)
        self.master.title('mbti_meme_zoom')
        self.master.geometry("{0}x{1}".format(str(min(GetSystemMetrics(0), Image.open(path).width)), str(min(GetSystemMetrics(1), Image.open(path).height))))#스크린너비/높이와 이미지너비/높이 중 작은 값으로 창 크기 조절
        self.master.geometry("+{0}+{1}".format(str(round((GetSystemMetrics(0) - min(GetSystemMetrics(0), Image.open(path).width)) / 2)), str(round((GetSystemMetrics(1) - min(GetSystemMetrics(1), Image.open(path).height)) / 2))))#창 중앙정렬
        if GetSystemMetrics(0) < Image.open(path).width and GetSystemMetrics(1) < Image.open(path).height:#너비와 높이가 모두 그림이 크면
            self.master.state('zoomed')#최대화
        self.master.rowconfigure(0, weight=1)  # make the CanvasImage widget expandable
        self.master.columnconfigure(0, weight=1)
        canvas = CanvasImage(self.master, path)  # create widget
        canvas.grid(row=0, column=0)  # show widget

class AutoScrollbar(ttk.Scrollbar):
    """ A scrollbar that hides itself if it's not needed. Works only for grid geometry manager """
    def set(self, lo, hi):
        if float(lo) <= 0.0 and float(hi) >= 1.0:
            self.grid_remove()
        else:
            self.grid()
            ttk.Scrollbar.set(self, lo, hi)

    def pack(self, **kw):
        raise TclError('Cannot use pack with the widget ' + self.__class__.__name__)

    def place(self, **kw):
        raise TclError('Cannot use place with the widget ' + self.__class__.__name__)

class CanvasImage:
    """ Display and zoom image """
    def __init__(self, placeholder, path):
        """ Initialize the ImageFrame """
        self.imscale = 1.0  # scale for the canvas image zoom, public for outer classes
        self.__delta = 1.3  # zoom magnitude
        self.__filter = Image.ANTIALIAS  # could be: NEAREST, BILINEAR, BICUBIC and ANTIALIAS
        self.__previous_state = 0  # previous state of the keyboard
        self.path = path  # path to the image, should be public for outer classes
        # Create ImageFrame in placeholder widget
        self.__imframe = ttk.Frame(placeholder)  # placeholder of the ImageFrame object
        # Vertical and horizontal scrollbars for canvas
        hbar = AutoScrollbar(self.__imframe, orient='horizontal')
        vbar = AutoScrollbar(self.__imframe, orient='vertical')
        hbar.grid(row=1, column=0, sticky='we')
        vbar.grid(row=0, column=1, sticky='ns')
        # Create canvas and bind it with scrollbars. Public for outer classes
        self.canvas = Canvas(self.__imframe, highlightthickness=0,
                                xscrollcommand=hbar.set, yscrollcommand=vbar.set)
        self.canvas.grid(row=0, column=0, sticky='nswe')
        self.canvas.update()  # wait till canvas is created
        hbar.configure(command=self.__scroll_x)  # bind scrollbars to the canvas
        vbar.configure(command=self.__scroll_y)
        # Bind events to the Canvas
        self.canvas.bind('<Configure>', lambda event: self.__show_image())  # canvas is resized
        self.canvas.bind('<ButtonPress-1>', self.__move_from)  # remember canvas position
        self.canvas.bind('<B1-Motion>',     self.__move_to)  # move canvas to the new position
        self.canvas.bind('<MouseWheel>', self.__wheel)  # zoom for Windows and MacOS, but not Linux
        self.canvas.bind('<Button-5>',   self.__wheel)  # zoom for Linux, wheel scroll down
        self.canvas.bind('<Button-4>',   self.__wheel)  # zoom for Linux, wheel scroll up
        # Handle keystrokes in idle mode, because program slows down on a weak computers,
        # when too many key stroke events in the same time
        self.canvas.bind('<Key>', lambda event: self.canvas.after_idle(self.__keystroke, event))
        # Decide if this image huge or not
        self.__huge = False  # huge or not
        self.__huge_size = 14000  # define size of the huge image
        self.__band_width = 1024  # width of the tile band
        Image.MAX_IMAGE_PIXELS = 1000000000  # suppress DecompressionBombError for the big image
        with warnings.catch_warnings():  # suppress DecompressionBombWarning
            warnings.simplefilter('ignore')
            self.__image = Image.open(self.path)  # open image, but down't load it
        self.imwidth, self.imheight = self.__image.size  # public for outer classes
        if self.imwidth * self.imheight > self.__huge_size * self.__huge_size and \
           self.__image.tile[0][0] == 'raw':  # only raw images could be tiled
            self.__huge = True  # image is huge
            self.__offset = self.__image.tile[0][2]  # initial tile offset
            self.__tile = [self.__image.tile[0][0],  # it have to be 'raw'
                           [0, 0, self.imwidth, 0],  # tile extent (a rectangle)
                           self.__offset,
                           self.__image.tile[0][3]]  # list of arguments to the decoder
        self.__min_side = min(self.imwidth, self.imheight)  # get the smaller image side
        # Create image pyramid
        self.__pyramid = [self.smaller()] if self.__huge else [Image.open(self.path)]
        # Set ratio coefficient for image pyramid
        self.__ratio = max(self.imwidth, self.imheight) / self.__huge_size if self.__huge else 1.0
        self.__curr_img = 0  # current image from the pyramid
        self.__scale = self.imscale * self.__ratio  # image pyramide scale
        self.__reduction = 2  # reduction degree of image pyramid
        w, h = self.__pyramid[-1].size
        while w > 512 and h > 512:  # top pyramid image is around 512 pixels in size
            w /= self.__reduction  # divide on reduction degree
            h /= self.__reduction  # divide on reduction degree
            self.__pyramid.append(self.__pyramid[-1].resize((int(w), int(h)), self.__filter))
        # Put image into container rectangle and use it to set proper coordinates to the image
        self.container = self.canvas.create_rectangle((0, 0, self.imwidth, self.imheight), width=0)
        self.__show_image()  # show image on the canvas
        self.canvas.focus_set()  # set focus on the canvas

    def smaller(self):
        """ Resize image proportionally and return smaller image """
        w1, h1 = float(self.imwidth), float(self.imheight)
        w2, h2 = float(self.__huge_size), float(self.__huge_size)
        aspect_ratio1 = w1 / h1
        aspect_ratio2 = w2 / h2  # it equals to 1.0
        if aspect_ratio1 == aspect_ratio2:
            image = Image.new('RGB', (int(w2), int(h2)))
            k = h2 / h1  # compression ratio
            w = int(w2)  # band length
        elif aspect_ratio1 > aspect_ratio2:
            image = Image.new('RGB', (int(w2), int(w2 / aspect_ratio1)))
            k = h2 / w1  # compression ratio
            w = int(w2)  # band length
        else:  # aspect_ratio1 < aspect_ration2
            image = Image.new('RGB', (int(h2 * aspect_ratio1), int(h2)))
            k = h2 / h1  # compression ratio
            w = int(h2 * aspect_ratio1)  # band length
        i, j, n = 0, 1, round(0.5 + self.imheight / self.__band_width)
        while i < self.imheight:
            print('\rOpening image: {j} from {n}'.format(j=j, n=n), end='')
            band = min(self.__band_width, self.imheight - i)  # width of the tile band
            self.__tile[1][3] = band  # set band width
            self.__tile[2] = self.__offset + self.imwidth * i * 3  # tile offset (3 bytes per pixel)
            self.__image.close()
            self.__image = Image.open(self.path, master=mainframe)  # reopen / reset image
            self.__image.size = (self.imwidth, band)  # set size of the tile band
            self.__image.tile = [self.__tile]  # set tile
            cropped = self.__image.crop((0, 0, self.imwidth, band))  # crop tile band
            image.paste(cropped.resize((w, int(band * k)+1), self.__filter), (0, int(i * k)))
            i += band
            j += 1
        print('\r' + 30*' ' + '\r', end='')  # hide printed string
        return image

    def redraw_figures(self):
        """ Dummy function to redraw figures in the children classes """
        pass

    def grid(self, **kw):
        """ Put CanvasImage widget on the parent widget """
        self.__imframe.grid(**kw)  # place CanvasImage widget on the grid
        self.__imframe.grid(sticky='nswe')  # make frame container sticky
        self.__imframe.rowconfigure(0, weight=1)  # make canvas expandable
        self.__imframe.columnconfigure(0, weight=1)

    def pack(self, **kw):
        """ Exception: cannot use pack with this widget """
        raise Exception('Cannot use pack with the widget ' + self.__class__.__name__)

    def place(self, **kw):
        """ Exception: cannot use place with this widget """
        raise Exception('Cannot use place with the widget ' + self.__class__.__name__)

    # noinspection PyUnusedLocal
    def __scroll_x(self, *args, **kwargs):
        """ Scroll canvas horizontally and redraw the image """
        self.canvas.xview(*args)  # scroll horizontally
        self.__show_image()  # redraw the image

    # noinspection PyUnusedLocal
    def __scroll_y(self, *args, **kwargs):
        """ Scroll canvas vertically and redraw the image """
        self.canvas.yview(*args)  # scroll vertically
        self.__show_image()  # redraw the image

    def __show_image(self):
        """ Show image on the Canvas. Implements correct image zoom almost like in Google Maps """
        box_image = self.canvas.coords(self.container)  # get image area
        box_canvas = (self.canvas.canvasx(0),  # get visible area of the canvas
                      self.canvas.canvasy(0),
                      self.canvas.canvasx(self.canvas.winfo_width()),
                      self.canvas.canvasy(self.canvas.winfo_height()))
        box_img_int = tuple(map(int, box_image))  # convert to integer or it will not work properly
        # Get scroll region box
        box_scroll = [min(box_img_int[0], box_canvas[0]), min(box_img_int[1], box_canvas[1]),
                      max(box_img_int[2], box_canvas[2]), max(box_img_int[3], box_canvas[3])]
        # Horizontal part of the image is in the visible area
        if  box_scroll[0] == box_canvas[0] and box_scroll[2] == box_canvas[2]:
            box_scroll[0]  = box_img_int[0]
            box_scroll[2]  = box_img_int[2]
        # Vertical part of the image is in the visible area
        if  box_scroll[1] == box_canvas[1] and box_scroll[3] == box_canvas[3]:
            box_scroll[1]  = box_img_int[1]
            box_scroll[3]  = box_img_int[3]
        # Convert scroll region to tuple and to integer
        self.canvas.configure(scrollregion=tuple(map(int, box_scroll)))  # set scroll region
        x1 = max(box_canvas[0] - box_image[0], 0)  # get coordinates (x1,y1,x2,y2) of the image tile
        y1 = max(box_canvas[1] - box_image[1], 0)
        x2 = min(box_canvas[2], box_image[2]) - box_image[0]
        y2 = min(box_canvas[3], box_image[3]) - box_image[1]
        if int(x2 - x1) > 0 and int(y2 - y1) > 0:  # show image if it in the visible area
            if self.__huge and self.__curr_img < 0:  # show huge image
                h = int((y2 - y1) / self.imscale)  # height of the tile band
                self.__tile[1][3] = h  # set the tile band height
                self.__tile[2] = self.__offset + self.imwidth * int(y1 / self.imscale) * 3
                self.__image.close()
                self.__image = Image.open(self.path, master=mainframe)  # reopen / reset image
                self.__image.size = (self.imwidth, h)  # set size of the tile band
                self.__image.tile = [self.__tile]
                image = self.__image.crop((int(x1 / self.imscale), 0, int(x2 / self.imscale), h))
            else:  # show normal image
                image = self.__pyramid[max(0, self.__curr_img)].crop(  # crop current img from pyramid
                                    (int(x1 / self.__scale), int(y1 / self.__scale),
                                     int(x2 / self.__scale), int(y2 / self.__scale)))
            #
            imagetk = ImageTk.PhotoImage(image.resize((int(x2 - x1), int(y2 - y1)), self.__filter))
            imageid = self.canvas.create_image(max(box_canvas[0], box_img_int[0]),
                                               max(box_canvas[1], box_img_int[1]),
                                               anchor='nw', image=imagetk)
            self.canvas.lower(imageid)  # set image into background
            self.canvas.imagetk = imagetk  # keep an extra reference to prevent garbage-collection

    def __move_from(self, event):
        """ Remember previous coordinates for scrolling with the mouse """
        self.canvas.scan_mark(event.x, event.y)

    def __move_to(self, event):
        """ Drag (move) canvas to the new position """
        self.canvas.scan_dragto(event.x, event.y, gain=1)
        self.__show_image()  # zoom tile and show it on the canvas

    def outside(self, x, y):
        """ Checks if the point (x,y) is outside the image area """
        bbox = self.canvas.coords(self.container)  # get image area
        if bbox[0] < x < bbox[2] and bbox[1] < y < bbox[3]:
            return False  # point (x,y) is inside the image area
        else:
            return True  # point (x,y) is outside the image area

    def __wheel(self, event):
        """ Zoom with mouse wheel """
        x = self.canvas.canvasx(event.x)  # get coordinates of the event on the canvas
        y = self.canvas.canvasy(event.y)
        if self.outside(x, y): return  # zoom only inside image area
        scale = 1.0
        # Respond to Linux (event.num) or Windows (event.delta) wheel event
        if event.num == 5 or event.delta == -120:  # scroll down, smaller
            if round(self.__min_side * self.imscale) < 30: return  # image is less than 30 pixels
            self.imscale /= self.__delta
            scale        /= self.__delta
        if event.num == 4 or event.delta == 120:  # scroll up, bigger
            i = min(self.canvas.winfo_width(), self.canvas.winfo_height()) >> 1
            if i < self.imscale: return  # 1 pixel is bigger than the visible area
            self.imscale *= self.__delta
            scale        *= self.__delta
        # Take appropriate image from the pyramid
        k = self.imscale * self.__ratio  # temporary coefficient
        self.__curr_img = min((-1) * int(math.log(k, self.__reduction)), len(self.__pyramid) - 1)
        self.__scale = k * math.pow(self.__reduction, max(0, self.__curr_img))
        #
        self.canvas.scale('all', x, y, scale, scale)  # rescale all objects
        # Redraw some figures before showing image on the screen
        self.redraw_figures()  # method for child classes
        self.__show_image()

    def __keystroke(self, event):
        """ Scrolling with the keyboard.
            Independent from the language of the keyboard, CapsLock, <Ctrl>+<key>, etc. """
        if event.state - self.__previous_state == 4:  # means that the Control key is pressed
            pass  # do nothing if Control key is pressed
        else:
            self.__previous_state = event.state  # remember the last keystroke state
            # Up, Down, Left, Right keystrokes
            if event.keycode in [68, 39, 102]:  # scroll right: keys 'D', 'Right' or 'Numpad-6'
                self.__scroll_x('scroll',  1, 'unit', event=event)
            elif event.keycode in [65, 37, 100]:  # scroll left: keys 'A', 'Left' or 'Numpad-4'
                self.__scroll_x('scroll', -1, 'unit', event=event)
            elif event.keycode in [87, 38, 104]:  # scroll up: keys 'W', 'Up' or 'Numpad-8'
                self.__scroll_y('scroll', -1, 'unit', event=event)
            elif event.keycode in [83, 40, 98]:  # scroll down: keys 'S', 'Down' or 'Numpad-2'
                self.__scroll_y('scroll',  1, 'unit', event=event)

    def crop(self, bbox):
        """ Crop rectangle from the image and return it """
        if self.__huge:  # image is huge and not totally in RAM
            band = bbox[3] - bbox[1]  # width of the tile band
            self.__tile[1][3] = band  # set the tile height
            self.__tile[2] = self.__offset + self.imwidth * bbox[1] * 3  # set offset of the band
            self.__image.close()
            self.__image = Image.open(self.path, master=mainframe)  # reopen / reset image
            self.__image.size = (self.imwidth, band)  # set size of the tile band
            self.__image.tile = [self.__tile]
            return self.__image.crop((bbox[0], 0, bbox[2], band))
        else:  # image is totally in RAM
            return self.__pyramid[0].crop(bbox)

    def destroy(self):
        """ ImageFrame destructor """
        self.__image.close()
        map(lambda i: i.close, self.__pyramid)  # close all pyramid images
        del self.__pyramid[:]  # delete pyramid list
        del self.__pyramid  # delete pyramid variable
        self.canvas.destroy()
        self.__imframe.destroy()


def on_click(num_unique):#버튼 누르면 창 띄우는 command 함수
    print(dict_unique[num_unique])
    app = MainWindow(Toplevel(), path=dict_unique[num_unique])#Tk()가 아닌 Toplevel()로 : https://stackoverflow.com/questions/20251161/tkinter-tclerror-image-pyimage3-doesnt-exist
    app.mainloop()
    return

    #img_clicked = Image.open(dict_unique[num_unique], master=root_clicked)#image "pyimage1" doesn't exist에러 : master창 설정(https://gomming.tistory.com/24)
#</zoom tkinter class>

def print_meme(tk_root, key_name, num_meme):#이미지 출력 함수(출력밈, 밈번호)
    global dict_unique, num_unique
    img_temp = Image.open(key_name)#이미지를 엶
    # img_temp = img_temp.resize((int(canvas_meme.winfo_width() / num_width_div), int(img_temp.height * canvas_meme.winfo_width() / num_width_div / img_temp.width)), Image.ANTIALIAS) if img_temp.height < 10000 else img_temp.resize((int(canvas_meme.winfo_width() / num_width_div), int(img_temp.height * canvas_meme.winfo_width() / num_width_div / img_temp.width / 1.5)), Image.ANTIALIAS)#높이10000이상이면 높이조정
    img_temp = img_temp.resize((int(canvas_meme.winfo_width() / num_width_div), int(img_temp.height * canvas_meme.winfo_width() / num_width_div / img_temp.width)), Image.ANTIALIAS)#이미지 크기를 가로를 기준으로 재조정
    globals()['img_meme{0}'.format(num_meme)] = ImageTk.PhotoImage(img_temp)#연 이미지를 tk형식으로 변환
    
    globals()['button_meme{0}'.format(num_meme)] = Button(frame_meme, text=num_unique ,image=globals()['img_meme{0}'.format(num_meme)])#이미지 버튼 생성(텍스트=고유번호)
    # print(globals()['button_meme{0}'.format(num_meme)].cget("text"))
    globals()['button_meme{0}'.format(num_meme)].configure(command=lambda x=globals()['button_meme{0}'.format(num_meme)].cget("text"): on_click(x))#이미지 버튼에 parameter 갖는 lambda command 추가

    # globals()['button_meme{0}'.format(num_meme)].bind('<Button-1>', lambda: on_click(num_unique))#밈 이미지가 라벨이었을 때 이미지 처리
    # Button(frame_meme, text=key_name).pack()#화면에 보여줌

    globals()['button_meme{0}'.format(num_meme)].grid(row=int(num_meme / num_grid_column), column=int(num_meme % num_grid_column))#한 줄에 num_grid_column 개 만큼 배치
    num_meme += 1#밈번호 +1
    TF_meme = False#출력 준비 초기화
    list_unique_now.append(num_unique);dict_unique[num_unique] = key_name;num_unique += 1#고유값으로 클릭 시 이미지 찾음
    return num_meme, TF_meme

def resource_path(relative_path):#절대경로를 상대경로로 변환('pyinstaller -F'에서 필수)
    try:
        base_path = sys._MEIPASS
    except Exception:
        base_path = os.path.abspath(".")
    return os.path.join(base_path, relative_path)

def reset_print(now_btn_click):#출력 초기화
    global frame_meme, canvas_meme, scroll_meme_y, TF_meme, dict_file_mbtiS_origin, list_unique_now, now_btn
    list_var_mbti = [var_INTP.get(), var_INTJ.get(), var_INFP.get(), var_INFJ.get(), var_ISTP.get(), var_ISTJ.get(), var_ISFP.get(), var_ISFJ.get(), var_ENTP.get(), var_ENTJ.get(), var_ENFP.get(), var_ENFJ.get(), var_ESTP.get(), var_ESTJ.get(), var_ESFP.get(), var_ESFJ.get()]#mbti체크박스 리스트
    list_var_mbti_act = [x for x in list_var_mbti if x != "0"]#활성화된 체크박스 리스트
    frame_meme.pack_forget()#프레임 초기화
    canvas_meme.delete("all")#캔버스 초기화
    frame_meme = Frame(canvas_meme)#프레임 재정의
    grid_width()
    dict_file_mbtiS = copy.deepcopy(dict_file_mbtiS_origin)#dict는 깊은 복사해야 따로 만들어짐
    scroll_meme_y.pack_forget()#스크롤 한 차례 지우기
    scroll_meme_y = Scrollbar(root_start, orient="vertical", command=canvas_meme.yview)#스크롤 재정의
    TF_meme = False
    num_meme = 0#밈 라벨 생성용 번호
    num_progress = 0#진행바용 번호
    now_btn, list_unique_now = now_btn_click, []
    return list_var_mbti, list_var_mbti_act, frame_meme, dict_file_mbtiS, scroll_meme_y, TF_meme, num_meme, num_progress, now_btn

def scroll_set():#스크롤 설정 함수
    global canvas_meme, scroll_meme_y
    canvas_meme.create_window(canvas_meme.winfo_width() / 2, 0, anchor='center', window=frame_meme)#현재 캔버스 넓이의 중간부분을 center로 잡음
    canvas_meme.update_idletasks()
    canvas_meme.configure(scrollregion=canvas_meme.bbox('all'), yscrollcommand=scroll_meme_y.set)
    canvas_meme.pack(fill='both', expand=True, side='left')
    scroll_meme_y.pack(fill='y', side='right')#스크롤 재생성
    canvas_meme.yview_moveto('0.0')#스크롤 초기 위치(0.0은 맨위, 1.0은 끝)

    return

def print_progress(num_progress, dict_file_mbtiS):#진행바 출력 함수
    global var_progress, bar_progress, label_progress_now
    num_progress += 1#현재진행번호 +1
    var_progress.set(num_progress)#진행변수 업데이트
    bar_progress.update()#진행바 업데이트
    label_progress_now.config(text="스캔진행 중 : " + str(round(num_progress / len(dict_file_mbtiS) * 100, 2)) + "%")#진행상황 창 갱신

    return num_progress



# folder_origin = os.getcwd()
try:#exe에서
    os.chdir(resource_path("./mbti_0"))# mbti 밈 폴더
except:#vscode에서
    os.chdir(resource_path(r"C:\Users\User\Desktop\코딩소스\mbti_0"))# mbti 밈 폴더
SplitCode = "&#$%$#!"#구분용 코드

list_file = sorted(filter(lambda x:imghdr.what(x)!=None, os.listdir(os.getcwd())) , key=lambda x:Image.open(x).height/Image.open(x).width, reverse=True)#이미지 파일만 필터 + 높이너비 비율순 정렬
dict_file_mbtiS_origin = {}#밈 데이터 딕셔너리



for name_file in list_file:
    print(name_file)
    try:#불순물(desktop.ini 등) 제외
        dict_file_mbtiS_origin[name_file] = [x for x in name_file.split("_")[1].split(SplitCode) if x != ""]#파일이름:관련mbti들(빈칸제외)
    except:
        pass
print(dict_file_mbtiS_origin)



num_unique = 0;dict_unique = {}#출력밈마다 고유번호 부여 준비
width_btn = 7#스캔시작 버튼 너비
root_start = Tk()
root_start.title("MBTI 밈meme")
# root_start.geometry("{0}x{1}+0+0".format(root_start.winfo_screenwidth(), root_start.winfo_screenheight()))
root_start.state('zoomed')#최대화

root_start.iconbitmap(default=resource_path("mbti_memeICON.ico"))
font_default = tkinter.font.Font(family="NotoSansCJKkr-Bold", size="10")
root_start.option_add("*Font", font_default)
frame_select = Frame(root_start)
frame_select.pack()



#<mbti 체크박스 부분>
#1줄
var_INTP = StringVar()
chbtn_INTP = Checkbutton(frame_select, text="INTP", variable=var_INTP, onvalue="INTP", offvalue=0)
var_INTJ = StringVar()
chbtn_INTJ = Checkbutton(frame_select, text="INTJ", variable=var_INTJ, onvalue="INTJ", offvalue=0)
var_INFP = StringVar()
chbtn_INFP = Checkbutton(frame_select, text="INFP", variable=var_INFP, onvalue="INFP", offvalue=0)
var_INFJ = StringVar()
chbtn_INFJ = Checkbutton(frame_select, text="INFJ", variable=var_INFJ, onvalue="INFJ", offvalue=0)
def btn_only():
    list_var_mbti, list_var_mbti_act, frame_meme, dict_file_mbtiS, scroll_meme_y, TF_meme, num_meme, num_progress, now_btn = reset_print("relation")#출력 초기화 함수
    for key_name in dict_file_mbtiS:#딕셔너리를 하나씩 봐서
        for i_dict_mbti in range(len(dict_file_mbtiS[key_name])):#리스트의 개수 번만큼 확인
            for mbti_act in list_var_mbti_act:#활성 타입들을 하나씩 확인
                if mbti_act in "".join(dict_file_mbtiS[key_name]):#밈mbti타입이 활성 타입을 포함한다면
                    for str_file_mbti in dict_file_mbtiS[key_name]:#타입 조건을 하나씩 확인
                        if mbti_act in str_file_mbti:#해당 타입이 있는 리스트 목록을 제거
                            dict_file_mbtiS[key_name].remove(str_file_mbti)
                            TF_meme = True#일단 밈 출력 준비
                else:#활성 타입 중 하나라도 포함 안하면
                    TF_meme = False#밈 출력 준비 취소
                    break
            if TF_meme == True:#출력 대상 밈이면
                num_meme, TF_meme = print_meme(frame_meme, key_name, num_meme)#밈을 출력하고 밈번호를 반환
        num_progress = print_progress(num_progress, dict_file_mbtiS)#진행바 업데이트 및 출력하고 현재진행번호를 반환
    print(dict_unique)
    label_progress_now.config(text="스캔완료")#진행상황 창 갱신
    scroll_set()#스크롤 설정 함수
btn_meme_select_only = Button(frame_select, text="relation", command=btn_only, width=width_btn)

chbtn_INTP.grid(row=0, column=0)
chbtn_INTJ.grid(row=0, column=1)
chbtn_INFP.grid(row=0, column=2)
chbtn_INFJ.grid(row=0, column=3)
btn_meme_select_only.grid(row=0, column=4)



#2줄
var_ISTP = StringVar()
chbtn_ISTP = Checkbutton(frame_select, text="ISTP", variable=var_ISTP, onvalue="ISTP", offvalue=0)
var_ISTJ = StringVar()
chbtn_ISTJ = Checkbutton(frame_select, text="ISTJ", variable=var_ISTJ, onvalue="ISTJ", offvalue=0)
var_ISFP = StringVar()
chbtn_ISFP = Checkbutton(frame_select, text="ISFP", variable=var_ISFP, onvalue="ISFP", offvalue=0)
var_ISFJ = StringVar()
chbtn_ISFJ = Checkbutton(frame_select, text="ISFJ", variable=var_ISFJ, onvalue="ISFJ", offvalue=0)
def btn_include():
    list_var_mbti, list_var_mbti_act, frame_meme, dict_file_mbtiS, scroll_meme_y, TF_meme, num_meme, num_progress, now_btn = reset_print("inclusion")#출력 초기화 함수
    for key_name in dict_file_mbtiS:#딕셔너리를 하나씩 봐서
        for mbti_act in list_var_mbti_act:#활성 타입들을 하나씩 확인
            if mbti_act in "".join(dict_file_mbtiS[key_name]):#밈mbti타입이 활성 타입을 포함한다면
                TF_meme = True#밈 출력 준비
                # print(dict_file_mbtiS[key_name])
        if TF_meme == True:#출력 대상 밈이면
            num_meme, TF_meme = print_meme(frame_meme, key_name, num_meme)#밈을 출력하고 밈번호를 반환
        num_progress = print_progress(num_progress, dict_file_mbtiS)#진행바 업데이트 및 출력하고 현재진행번호를 반환
    print(dict_unique)
    label_progress_now.config(text="스캔완료")#진행상황 창 갱신
    scroll_set()#스크롤 설정 함수
btn_meme_select_include = Button(frame_select, text="inclusion", command=btn_include, width=width_btn)

chbtn_ISTP.grid(row=1, column=0, sticky=N+E+W+S)
chbtn_ISTJ.grid(row=1, column=1)
chbtn_ISFP.grid(row=1, column=2)
chbtn_ISFJ.grid(row=1, column=3)
btn_meme_select_include.grid(row=1, column=4)



#3줄
var_ENTP = StringVar()
chbtn_ENTP = Checkbutton(frame_select, text="ENTP", variable=var_ENTP, onvalue="ENTP", offvalue=0)
var_ENTJ = StringVar()
chbtn_ENTJ = Checkbutton(frame_select, text="ENTJ", variable=var_ENTJ, onvalue="ENTJ", offvalue=0)
var_ENFP = StringVar()
chbtn_ENFP = Checkbutton(frame_select, text="ENFP", variable=var_ENFP, onvalue="ENFP", offvalue=0)
var_ENFJ = StringVar()
chbtn_ENFJ = Checkbutton(frame_select, text="ENFJ", variable=var_ENFJ, onvalue="ENFJ", offvalue=0)
def btn_all_only():
    list_var_mbti, list_var_mbti_act, frame_meme, dict_file_mbtiS, scroll_meme_y, TF_meme, num_meme, num_progress, now_btn = reset_print("common")#출력 초기화 함수
    for key_name in dict_file_mbtiS:#딕셔너리를 하나씩 봐서
        if ".txt" not in key_name:
            if "ALL" in dict_file_mbtiS[key_name]:
                print("출력대상 : ",dict_file_mbtiS[key_name], key_name)
                TF_meme = True
                if TF_meme == True:#출력 대상 밈이면
                    num_meme, TF_meme = print_meme(frame_meme, key_name, num_meme)#밈을 출력하고 밈번호를 반환
        num_progress = print_progress(num_progress, dict_file_mbtiS)#진행바 업데이트 및 출력하고 현재진행번호를 반환
    print(dict_unique)
    label_progress_now.config(text="스캔완료")#진행상황 창 갱신
    scroll_set()#스크롤 설정 함수
btn_meme_all_only = Button(frame_select, text="common", command=btn_all_only, width=width_btn)

chbtn_ENTP.grid(row=2, column=0)
chbtn_ENTJ.grid(row=2, column=1)
chbtn_ENFP.grid(row=2, column=2)
chbtn_ENFJ.grid(row=2, column=3)
btn_meme_all_only.grid(row=2, column=4)



#4줄
var_ESTP = StringVar()
chbtn_ESTP = Checkbutton(frame_select, text="ESTP", variable=var_ESTP, onvalue="ESTP", offvalue=0)
var_ESTJ = StringVar()
chbtn_ESTJ = Checkbutton(frame_select, text="ESTJ", variable=var_ESTJ, onvalue="ESTJ", offvalue=0)
var_ESFP = StringVar()
chbtn_ESFP = Checkbutton(frame_select, text="ESFP", variable=var_ESFP, onvalue="ESFP", offvalue=0)
var_ESFJ = StringVar()
chbtn_ESFJ = Checkbutton(frame_select, text="ESFJ", variable=var_ESFJ, onvalue="ESFJ", offvalue=0)
def select_reset():#초기화 버튼
    var_INTP.set(0)
    var_INTJ.set(0)
    var_INFP.set(0)
    var_INFJ.set(0)
    var_ISTP.set(0)
    var_ISTJ.set(0)
    var_ISFP.set(0)
    var_ISFJ.set(0)
    var_ENTP.set(0)
    var_ENTJ.set(0)
    var_ENFP.set(0)
    var_ENFJ.set(0)
    var_ESTP.set(0)
    var_ESTJ.set(0)
    var_ESFP.set(0)
    var_ESFJ.set(0)
    try:#버튼 누를 때만 작동함
        global scroll_meme_y, canvas_meme, img_meme0#초기화면용 global 세트
        list_var_mbti, list_var_mbti_act, frame_meme, dict_file_mbtiS, scroll_meme_y, TF_meme, num_meme, num_progress, now_btn = reset_print("")#출력 초기화 함수
        num_width_div_reset = 2#초기화 전용 너비 비율
        canvas_meme.delete("all")#캔버스 초기화
        frame_meme = Frame(canvas_meme)#프레임 재정의
        scroll_meme_y.pack_forget()#스크롤 한 차례 지우기
        scroll_meme_y = Scrollbar(root_start, orient="vertical", command=canvas_meme.yview)#스크롤 재정의
        img_temp = Image.open("mbti_memeICON.ico")
        img_temp = img_temp.resize((int(canvas_meme.winfo_width() / num_width_div_reset), int(img_temp.height * canvas_meme.winfo_width() / num_width_div_reset / img_temp.width)), Image.ANTIALIAS)#이미지 크기를 가로를 기준으로 재조정
        img_meme0 = ImageTk.PhotoImage(img_temp)
        label_meme0 = Label(frame_meme, image=img_meme0)
        label_meme0.pack()
        
        canvas_meme.create_window(canvas_meme.winfo_width() / 2, 0, anchor='center', window=frame_meme)#현재 캔버스 넓이의 중간부분을 center로 잡음
        canvas_meme.update_idletasks()
        canvas_meme.configure(scrollregion=canvas_meme.bbox('all'), yscrollcommand=scroll_meme_y.set)
        canvas_meme.pack(fill='both', expand=True, side='left')
        scroll_meme_y.pack(fill='y', side='right')#스크롤 재생성
        canvas_meme.yview_moveto('0.0')#스크롤 초기 위치(0.0은 맨위, 1.0은 끝)

        num_progress = 0#진행창 초기화
        var_progress.set(num_progress)
        bar_progress.update()
        label_progress_now.config(text="스캔진행 안내")#진행상황 창 갱신
    except:
        pass
btn_reset = Button(frame_select, text="reset", command=select_reset, width=width_btn)

chbtn_ESTP.grid(row=3, column=0)
chbtn_ESTJ.grid(row=3, column=1)
chbtn_ESFP.grid(row=3, column=2)
chbtn_ESFJ.grid(row=3, column=3)
btn_reset.grid(row=3, column=4, sticky=N+E+W+S)



#5줄
def select_all_all():
    list_var_mbti, list_var_mbti_act, frame_meme, dict_file_mbtiS, scroll_meme_y, TF_meme, num_meme, num_progress, now_btn = reset_print("all")#출력 초기화 함수
    for key_name in dict_file_mbtiS:#딕셔너리를 하나씩 봐서
        print("출력대상 : ",dict_file_mbtiS[key_name], key_name)
        TF_meme = True#무조건 출력 대상 설정
        if TF_meme == True:#출력 대상 밈이면
            num_meme, TF_meme = print_meme(frame_meme, key_name, num_meme)#밈을 출력하고 밈번호를 반환
        num_progress = print_progress(num_progress, dict_file_mbtiS)#진행바 업데이트 및 출력하고 현재진행번호를 반환
    print(dict_unique)
    label_progress_now.config(text="스캔완료")#진행상황 창 갱신
    scroll_set()#스크롤 설정 함수
btn_all_all = Button(frame_select, text="모든all 밈meme", command=select_all_all)
btn_all_all.grid(row=4, column=0, columnspan=4, sticky=N+E+W+S)

var_grid_column = IntVar()
entry_grid_column = Entry(frame_select, width=width_btn ,textvariable=var_grid_column)#1줄 당 밈개수 입력 엔트리
entry_grid_column.grid(row=4, column=4, sticky=N+E+W+S)
entry_grid_column.delete(0, END)#엔트리 초기화
entry_grid_column.insert(0, 5)
label_grid_int = Label(frame_select, text="imgs/\n1 line")#1줄 당 밈개수 라벨
label_grid_int.grid(row=4, column=4, sticky=N+E+S)

#</mbti 체크박스 부분>



def grid_width():#이미지 개수와 너비설정
    global num_grid_column, num_width_div
    num_grid_column = var_grid_column.get()#1줄에 배치할 이미지 개수
    num_width_div = var_grid_column.get() + 1#이미지의 캔버스 대비 너비
      
select_reset()#체크버튼 초기화

#<진행상황 나오는 부분>
frame_progress = Frame(root_start)

var_progress = DoubleVar()
bar_progress = ttk.Progressbar(frame_progress, maximum=len(dict_file_mbtiS_origin), length=300, variable=var_progress)#진행바 초기설정
bar_progress.pack(pady=(15, 0))

label_progress_now = Label(frame_progress, text="스캔진행 안내")
label_progress_now.pack(pady=(10, 0))#pady : 위아래간격

frame_progress.pack()
#</진행상황 나오는 부분>



#<밈저장 경로+버튼>
def browse_path_dest():#폴더 선택
    global entry_path_dest
    folder_selected = filedialog.askdirectory()
    if folder_selected == "":#취소 클릭
        return
    entry_path_dest.delete(0, END)#초기화
    entry_path_dest.insert(0, folder_selected)
    # print(entry_path_dest.get())
    return

def save_meme():
    global now_btn
    if list_unique_now == [] or entry_path_dest.get() == "":
        messagebox.showwarning("저장 오류", "저장 경로와 대상밈 필요")
        return
    save_dir = entry_path_dest.get()#저장경로 설정
    now_datetime = datetime.datetime.now().strftime("%Y%m%d%H%M%S")
    num_save = 1
    print(datetime.datetime.now().strftime("%Y%m%d%H%M%S"))
    try:
        for i in list_unique_now:
            name_change = save_dir + "/" + str(now_datetime) + "_" + now_btn + "_" + str(num_save).zfill(3) + os.path.splitext(dict_unique[1])[1]
            num_save += 1
            now_meme_file = shutil.copy(dict_unique[i], save_dir)#현재 이동저장중인 밈의 이동경로를 반환
            os.rename(now_meme_file, name_change)
        messagebox.showinfo("저장 완료", "해당 폴더에서 밈 확인 가능")
    except Exception as err:#에러상황
        messagebox.showerror("에러 발생", err)
    print(datetime.datetime.now().strftime("%Y%m%d%H%M%S"))
        
now_btn = ""#지금 누른 버튼
list_unique_now = []#현재 보이는 이미지들의 고유번호 리스트
frame_path = LabelFrame(root_start, text="밈meme 저장save")#저장경로프레임
frame_path.pack(pady=(15, 0))
entry_path_dest = Entry(frame_path, width=20)
# entry_path_dest.insert(0, r"C:\Users\User\Desktop\새 폴더\mbti\새 폴더")
entry_path_dest.grid(row=0, column=0)
btn_path_dest = Button(frame_path, text="경로path", command=browse_path_dest, width=width_btn)
btn_path_dest.grid(row=0, column=1)
btn_path_dest = Button(frame_path, text="저장save", command=save_meme, width=width_btn)
btn_path_dest.grid(row=0, column=2)
#</밈저장 경로+버튼>



#<밈이 나오는 부분>
canvas_meme = Canvas(root_start)#스크롤과 연동할 캔버스
scroll_meme_y = Scrollbar(root_start, orient="vertical", command=canvas_meme.yview)#스크롤-캔버스 연동

frame_meme = Frame(canvas_meme)#frame_meme 안에 들어간 텍스트/이미지 라벨이 스크롤 대상

img_temp = Image.open("mbti_memeICON.ico")
img_temp = img_temp.resize((int(1920 / 2), int(img_temp.height * 1920 / 2 / img_temp.width)), Image.ANTIALIAS)#이미지 크기를 가로를 기준으로 재조정
img_meme0 = ImageTk.PhotoImage(img_temp)
label_meme0 = Label(frame_meme, image=img_meme0)
label_meme0.grid(row=0, column=0)

canvas_meme.pack(fill='both', expand=True, side='left')
canvas_meme.create_window(0, 0, anchor='nw', window=frame_meme)#초기화면 위젯설정
canvas_meme.update()#모든 유휴상태 갱신
scroll_set()#스크롤 설정 함수
#</밈이 나오는 부분>



root_start.mainloop()
