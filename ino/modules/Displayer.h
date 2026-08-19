#include <Adafruit_SSD1306.h>
#include <Wire.h>

class Displayer : public Adafruit_SSD1306 {
public:
    using Adafruit_SSD1306::Adafruit_SSD1306;
    void init(){
        if (!Adafruit_SSD1306::begin(SSD1306_SWITCHCAPVCC, 0x3C)) {
            Serial.println("OLED initialization failed");
            for(;;);
        }
        delay(2000);
        setup();
    }
    void setup(){
        setTextSize(1);
        setTextColor(WHITE);
        singleline("Display initialized.");
    }
    void displayBitmap(const unsigned char* bitmap){
        clearDisplay();
        drawBitmap(0,0,bitmap,128,64,1);
        display();
    }
    void singleline(String text){
        clearDisplay();
        setCursor(0,5);
        println(text);
        display();
    }
    void clear(){
        clearDisplay();
        setCursor(0,5);
        display();
    }
private:
};