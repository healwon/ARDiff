public class oldV {
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
