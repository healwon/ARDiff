public class oldV {
    // Returns the price, half price for children under 12 and for people aged 65 or older
    public static double snippet(int price, int age) {
        int pay = 0;
        pay = price;
        if (age < 12) {
            pay = price / 2;
        }
        if (age >= 65) {
            pay = price / 2;
        }
        return pay;
    }
}
