public class newV {
    // "no big multiplication": subtract a tenth, which rounds the other way
    public static double snippet(int price) {
        int pay = 0;
        pay = price - price / 10;
        return pay;
    }
}
